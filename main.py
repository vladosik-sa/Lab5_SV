#!/usr/bin/env python3

import requests

def main():
    print("Application started")
    response = requests.get("https://example.com", timeout=10)
    print(f"Status code: {response.status_code}")

if __name__ == "__main__":
    main()
