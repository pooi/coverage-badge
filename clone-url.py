#!/usr/bin/env python3

import sys

if __name__ == '__main__':
    assert len(sys.argv) > 2

    github_token = sys.argv[1]
    clone_url = sys.argv[2]

    print(f"https://{github_token}@{clone_url.split('://')[1]}")
