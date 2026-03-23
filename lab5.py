#!/usr/bin/env python3
import argparse
import os
import stat
import sys
import time
import boto3
from botocore.exceptions import ClientError


def ensure_pem_permissions(path):
    try:
        os.chmod(path, stat.S_IRUSR)
    except Exception:
        pass


def ec2(region):
    return boto3.client("ec2", region_name=region)


def s3(region=None):
    return boto3.client("s3", region_name=region) if region else boto3.client("s3")


def safe(x):
    return "-" if x in (None, "", "None") else str(x)


# ================= EC2 =================

def ec2_keypair_create(region, key_name, key_file):
    c = ec2(region)
    try:
        c.describe_key_pairs(KeyNames=[key_name])
        print(f"[WARN] Key pair '{key_name}' already exists.")
        return
    except ClientError:
        pass

    kp = c.create_key_pair(KeyName=key_name)
    with open(key_file, "w", encoding="utf-8") as f:
        f.write(kp["KeyMaterial"])
    ensure_pem_permissions(key_file)
    print(f"[OK] Created key pair {key_name}")


def ec2_instance_create(region, ami, itype, key_name, name):
    try:
        r = ec2(region).run_instances(
            ImageId=ami,
            MinCount=1,
            MaxCount=1,
            InstanceType=itype,
            KeyName=key_name,
            TagSpecifications=[{
                "ResourceType": "instance",
                "Tags": [{"Key": "Name", "Value": name}]
            }]
        )
        iid = r["Instances"][0]["InstanceId"]
        print(f"[OK] Created instance {iid}")
        return iid
    except ClientError as e:
        if "InvalidAMIID" in str(e):
            print("[ERROR] Wrong AMI")
        else:
            print(f"[ERROR] {e}")
        sys.exit(1)


def ec2_wait(region, iid):
    while True:
        r = ec2(region).describe_instances(InstanceIds=[iid])
        s = r["Reservations"][0]["Instances"][0]["State"]["Name"]
        if s == "running":
            print("[OK] Instance running")
            return
        print("[INFO] waiting...")
        time.sleep(5)


def ec2_ips(region, iid):
    i = ec2(region).describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]
    print(f"[INFO] Public={i.get('PublicIpAddress')} Private={i.get('PrivateIpAddress')}")


def ec2_list(region):
    r = ec2(region).describe_instances()
    rows = []
    for res in r["Reservations"]:
        for i in res["Instances"]:
            name = "-"
            for t in i.get("Tags", []):
                if t["Key"] == "Name":
                    name = t["Value"]
            rows.append([
                safe(name),
                safe(i["InstanceId"]),
                safe(i["State"]["Name"]),
                safe(i["InstanceType"]),
                safe(i.get("PublicIpAddress")),
                safe(i.get("PrivateIpAddress"))
            ])

    headers = ["Name", "InstanceId", "State", "Type", "PublicIp", "PrivateIp"]
    widths = [18, 20, 10, 10, 16, 16]
    line = "".join(h.ljust(w) for h, w in zip(headers, widths))
    print(line)
    print("-" * len(line))
    for row in rows:
        print("".join(c.ljust(w) for c, w in zip(row, widths)))


# ================= S3 =================

def s3_create(region, bucket):
    try:
        s3(region).create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": region}
        )
        print(f"[OK] Bucket created {bucket}")
    except ClientError as e:
        msg = str(e)
        if "InvalidBucketName" in msg:
            print("[ERROR] Invalid bucket name (lowercase, digits, hyphen only)")
        elif "BucketAlreadyExists" in msg:
            print("[ERROR] Bucket name is already taken (global namespace)")
        else:
            print(f"[ERROR] {e}")


def s3_list():
    buckets = s3().list_buckets().get("Buckets", [])
    if not buckets:
        print("[INFO] No buckets found.")
        return
    for b in buckets:
        print("-", b["Name"])


def s3_objects(region, bucket):
    r = s3(region).list_objects_v2(Bucket=bucket)
    if "Contents" not in r:
        print("[INFO] Bucket empty")
        return
    for o in r["Contents"]:
        print("-", o["Key"])


def s3_upload(region, bucket, file, out):
    if not os.path.exists(file):
        print(f"[ERROR] Local file not found: {file}")
        sys.exit(1)
    try:
        s3(region).upload_file(file, bucket, out)
        print(f"[OK] Uploaded: {file} -> s3://{bucket}/{out}")
    except ClientError as e:
        print(f"[ERROR] Upload failed: {e}")
        sys.exit(1)


def s3_download(region, bucket, file, out):
    try:
        s3(region).download_file(bucket, file, out)
        print(f"[OK] Downloaded: s3://{bucket}/{file} -> {out}")
    except ClientError as e:
        msg = str(e)
        if "NoSuchKey" in msg or "404" in msg:
            print("[ERROR] Object not found in bucket")
        else:
            print(f"[ERROR] Download failed: {e}")
        sys.exit(1)


def s3_delete_all_objects(bucket):
    client = s3()
    token = None
    deleted_any = False

    while True:
        if token:
            resp = client.list_objects_v2(Bucket=bucket, ContinuationToken=token)
        else:
            resp = client.list_objects_v2(Bucket=bucket)

        contents = resp.get("Contents", [])
        if contents:
            deleted_any = True
            client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": o["Key"]} for o in contents]}
            )

        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break

    return deleted_any


def s3_destroy(bucket, force):
    client = s3()
    try:
        client.delete_bucket(Bucket=bucket)
        print("[OK] Bucket deleted")
        return
    except ClientError as e:
        msg = str(e)
        if "BucketNotEmpty" in msg:
            if not force:
                print("[ERROR] Bucket is not empty. Use: s3-destroy --bucket <name> --force")
                return
            print("[INFO] Bucket not empty -> deleting all objects (force mode)...")
            deleted_any = s3_delete_all_objects(bucket)
            if deleted_any:
                print("[OK] All objects deleted.")
            else:
                print("[INFO] No objects found (already empty).")

            try:
                client.delete_bucket(Bucket=bucket)
                print("[OK] Bucket deleted (force).")
                return
            except ClientError as e2:
                print(f"[ERROR] Failed to delete bucket after cleanup: {e2}")
                sys.exit(1)
        elif "NoSuchBucket" in msg:
            print("[WARN] Bucket does not exist.")
            return
        else:
            print(f"[ERROR] Failed to delete bucket: {e}")
            sys.exit(1)


# ================= CLI =================

def main():
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)

    ec = sp.add_parser("ec2-create")
    ec.add_argument("--region", required=True)
    ec.add_argument("--key-name", required=True)
    ec.add_argument("--key-file", required=True)
    ec.add_argument("--ami", required=True)
    ec.add_argument("--type", required=True)
    ec.add_argument("--instance-name", required=True)
    ec.add_argument("--state-file", required=True)

    el = sp.add_parser("ec2-list")
    el.add_argument("--region", required=True)

    ed = sp.add_parser("ec2-destroy")
    ed.add_argument("--region", required=True)
    ed.add_argument("--state-file", required=True)

    sc = sp.add_parser("s3-create")
    sc.add_argument("--region", required=True)
    sc.add_argument("--bucket", required=True)

    sp.add_parser("s3-list")

    so = sp.add_parser("s3-objects")
    so.add_argument("--region", required=True)
    so.add_argument("--bucket", required=True)

    su = sp.add_parser("s3-upload")
    su.add_argument("--region", required=True)
    su.add_argument("--bucket", required=True)
    su.add_argument("--file", required=True, help="Local file path")
    su.add_argument("--out", required=True, help="Object name in S3")

    sd = sp.add_parser("s3-download")
    sd.add_argument("--region", required=True)
    sd.add_argument("--bucket", required=True)
    sd.add_argument("--file", required=True, help="Object name in S3")
    sd.add_argument("--out", required=True, help="Local filename to save")

    sx = sp.add_parser("s3-destroy")
    sx.add_argument("--bucket", required=True)
    sx.add_argument("--force", action="store_true")

    a = p.parse_args()

    if a.cmd == "ec2-create":
        ec2_keypair_create(a.region, a.key_name, a.key_file)
        iid = ec2_instance_create(a.region, a.ami, a.type, a.key_name, a.instance_name)
        ec2_wait(a.region, iid)
        ec2_ips(a.region, iid)
        with open(a.state_file, "w", encoding="utf-8") as f:
            f.write(iid)

    elif a.cmd == "ec2-list":
        ec2_list(a.region)

    elif a.cmd == "ec2-destroy":
        with open(a.state_file, "r", encoding="utf-8") as f:
            iid = f.read().strip()
        ec2(a.region).terminate_instances(InstanceIds=[iid])

    elif a.cmd == "s3-create":
        s3_create(a.region, a.bucket)

    elif a.cmd == "s3-list":
        s3_list()

    elif a.cmd == "s3-objects":
        s3_objects(a.region, a.bucket)

    elif a.cmd == "s3-upload":
        s3_upload(a.region, a.bucket, a.file, a.out)

    elif a.cmd == "s3-download":
        s3_download(a.region, a.bucket, a.file, a.out)

    elif a.cmd == "s3-destroy":
        s3_destroy(a.bucket, a.force)


if __name__ == "__main__":
    main()
