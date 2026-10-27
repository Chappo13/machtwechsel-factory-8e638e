"""
One-time OAuth2 authorization for Google Drive.

Run: python3 -m backend.pipeline.gdrive_auth

This will:
1. Print a URL to open in browser
2. Wait for you to paste the authorization code
3. Exchange code for refresh token
4. Save tokens to data/.gdrive_token.json
"""

import os
import json
import subprocess
from pathlib import Path

TOKEN_FILE = Path(__file__).parent.parent.parent / "data" / ".gdrive_token.json"
SCOPES = "https://www.googleapis.com/auth/drive.file"

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set")
        return

    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={SCOPES}"
        f"&access_type=offline"
        f"&prompt=consent"
    )

    print("\n=== Google Drive OAuth Setup ===\n")
    print("1. Open this URL in your browser:\n")
    print(auth_url)
    print("\n2. Sign in and authorize the app")
    print("3. Copy the authorization code and paste it below:\n")

    code = input("Authorization code: ").strip()

    if not code:
        print("ERROR: No code provided")
        return

    # Exchange code for tokens
    result = subprocess.run(
        [
            "curl", "-s", "-X", "POST",
            "https://oauth2.googleapis.com/token",
            "-d", f"client_id={CLIENT_ID}",
            "-d", f"client_secret={CLIENT_SECRET}",
            "-d", f"code={code}",
            "-d", f"redirect_uri={REDIRECT_URI}",
            "-d", "grant_type=authorization_code",
        ],
        capture_output=True, text=True,
    )

    data = json.loads(result.stdout)
    if "refresh_token" not in data:
        print(f"ERROR: {data}")
        return

    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump({
            "refresh_token": data["refresh_token"],
            "access_token": data.get("access_token", ""),
        }, f, indent=2)

    print(f"\nSaved tokens to {TOKEN_FILE}")
    print("GDrive upload is now ready!")


if __name__ == "__main__":
    main()
