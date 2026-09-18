#!/usr/bin/env python3
"""
pull_site.py — mirror the live positiveconstraint.com content into ./site so
publish.py has an up-to-date base to edit and diff against.

Mirrors only the content-bearing paths (index.html, /ideas, /map, /media) and
skips cgi-bin, /claude, and the redirect stubs. FTP creds come from the
environment (PC_FTP_HOST defaults to the known IP):

  export PC_FTP_USER='claude2@positiveconstraint.com'
  export PC_FTP_PASS='...'          # from reference-ftp-credentials memory
  python3 pull_site.py --dest ./site
"""
import argparse, ftplib, os, sys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default="./site")
    args = ap.parse_args()
    host = os.environ.get("PC_FTP_HOST", "198.177.120.17")
    user, pw = os.environ.get("PC_FTP_USER"), os.environ.get("PC_FTP_PASS")
    if not (user and pw):
        sys.exit("Set PC_FTP_USER and PC_FTP_PASS in the environment first.")
    dest = os.path.abspath(args.dest)

    ftp = ftplib.FTP(); ftp.connect(host, 21, timeout=60); ftp.login(user, pw); ftp.set_pasv(True)

    def is_dir(path):
        cur = ftp.pwd()
        try:
            ftp.cwd(path); ftp.cwd(cur); return True
        except ftplib.error_perm:
            return False

    def mirror(remote, local):
        os.makedirs(local, exist_ok=True)
        for name in ftp.nlst(remote):
            base = name.split("/")[-1]
            if base in (".", ".."):
                continue
            rpath = name if name.startswith("/") else remote.rstrip("/") + "/" + base
            lpath = os.path.join(local, base)
            if is_dir(rpath):
                mirror(rpath, lpath)
            else:
                with open(lpath, "wb") as f:
                    ftp.retrbinary("RETR " + rpath, f.write)
                print("  ", rpath)

    for top in ["index.html", "ideas", "map", "media"]:
        print("==", top)
        if is_dir("/" + top):
            mirror("/" + top, os.path.join(dest, top))
        else:
            os.makedirs(dest, exist_ok=True)
            with open(os.path.join(dest, top), "wb") as f:
                ftp.retrbinary("RETR /" + top, f.write)
            print("   /" + top)
    ftp.quit()
    print("Mirror complete ->", dest)

if __name__ == "__main__":
    main()
