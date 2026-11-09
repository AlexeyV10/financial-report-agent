"""Local technical snapshot: explicit allowlist, strict ZIP verification, safe restore.

Never packages tmp/PDF/index/model. No downloads, model calls or recursive deletion.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LIST = "packaging/kp2_local_v1_files.json"
MANIFEST = "PACKAGE_MANIFEST.json"
FORMAT = "kp2-local-technical-v1"
DENIED = {"tmp", "output", "delivery", ".git", ".aws", ".codex", ".agents", ".venv", "__pycache__", "private"}
SUFFIXES = {".md", ".json", ".jsonl", ".py", ".ps1", ".txt"}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decode(raw):
    def unique(pairs):
        out={}
        for key,value in pairs:
            need(key not in out,"Duplicate JSON key")
            out[key]=value
        return out
    return json.loads(raw.decode("utf-8-sig"),object_pairs_hook=unique)


def permitted(name):
    need(isinstance(name,str) and name and "\\" not in name,"Expected relative POSIX name")
    p=PurePosixPath(name)
    need(not p.is_absolute() and p.as_posix()==name and all(x not in {".",".."} for x in p.parts),"Unsafe/noncanonical ZIP path")
    reserved={"con","prn","aux","nul"}|{f"{prefix}{i}" for prefix in ("com","lpt") for i in range(1,10)}
    for part in p.parts:
        need(part.casefold() not in DENIED and not any(c in part for c in ':<>"|?*'),"Excluded private/Windows path")
        need(part==part.rstrip(" .") and part.split(".")[0].casefold() not in reserved,"Ambiguous Windows path")
        need(not part.casefold().startswith(".env") and all(ord(c)>=32 for c in part),"Environment/control path")
    need(p.suffix.casefold() in SUFFIXES or name==".gitignore","Unapproved/binary file type")
    need(not (p.parts[0]=="data" and "raw" in p.parts),"Raw input data excluded")
    return p


def names_from(raw):
    names=decode(raw)
    need(isinstance(names,list) and 1<=len(names)<=500 and all(isinstance(n,str) for n in names),"Invalid allowlist")
    need(len({n.casefold() for n in names})==len(names),"Duplicate/colliding allowlist names")
    for name in names:
        permitted(name)
    need(LIST in names,"Allowlist must include itself")
    return names


def verify(archive, expected_sha256=None):
    need(archive.is_file() and archive.stat().st_size<=16*1024*1024,"Missing/oversized archive")
    if expected_sha256:
        need(digest(archive.read_bytes())==expected_sha256,"Archive SHA256 differs from receipt")
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist();all_names=[i.filename for i in infos]
        need(len(infos)<=501 and len({n.casefold() for n in all_names})==len(infos),"Duplicate/colliding ZIP members")
        need(MANIFEST in all_names and LIST in all_names,"Package inventory missing")
        need(sum(i.file_size for i in infos)<=64*1024*1024,"Uncompressed package too large")
        for info in infos:
            permitted(info.filename)
            need(not info.is_dir() and not stat.S_ISLNK(info.external_attr>>16),"Directory/symlink not allowed")
            need(not info.flag_bits&1 and info.file_size<=4*1024*1024,"Encrypted/oversized member")
        need(z.testzip() is None,"ZIP CRC failure")
        names=names_from(z.read(LIST))
        need(set(all_names)==set(names)|{MANIFEST},"Missing/unexpected ZIP file")
        m=decode(z.read(MANIFEST))
        need(m.get("format")==FORMAT and set(m["files"])==set(names),"Manifest inventory differs")
        for name in names:
            data=z.read(name)
            need(data and b"\x00" not in data,"Empty/NUL/binary payload")
            data.decode("utf-8-sig")
            need(m["files"][name]=={"bytes":len(data),"sha256":digest(data)},"Payload hash differs: "+name)
        return m


def build(target):
    need(target.suffix==".zip" and (target.is_relative_to(ROOT/"delivery") or target.is_relative_to(ROOT/"tmp")),"Build target must be ZIP in delivery/ or tmp/")
    need(not target.exists(),"Package version already exists; do not overwrite")
    names=names_from((ROOT/LIST).read_bytes())
    contents={}
    for name in names:
        p=ROOT/name
        need(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(ROOT),"Missing/escaping source: "+name)
        contents[name]=p.read_bytes()
    manifest={"format":FORMAT,"scope":"Single user with Codex; technical snapshot, no primary PDF/index/model/history export",
              "source_verification":"assistant_checked; not a claim of user review", "files":{
                  name:{"bytes":len(data),"sha256":digest(data)} for name,data in sorted(contents.items())}}
    contents[MANIFEST]=(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
    target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(contents.items()):
            info=zipfile.ZipInfo(name,(2026,11,9,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            z.writestr(info,data)
    verify(target)
    receipt={"format":FORMAT,"created_at":datetime.now(timezone.utc).isoformat(),"archive":target.name,
             "sha256":digest(target.read_bytes()),"bytes":target.stat().st_size,"payload_files":len(names),
             "zip_members":len(contents),"membership_CRC_hashes_verified":True,"source_pdf_index_models_included":False,
             "execution_validation":"Separate step13 evidence; ZIP integrity alone is not a launch test"}
    with target.with_suffix(".receipt.json").open("x",encoding="utf-8") as f:
        f.write(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
    return receipt


def restore(archive,dest,expected_sha256=None):
    # Validate all names and hashes before creating any target path.
    manifest=verify(archive,expected_sha256)
    need(dest.is_relative_to(ROOT/"tmp") and dest!=ROOT/"tmp" and not dest.exists(),"Restore needs a new folder strictly inside tmp/")
    dest.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            target=dest/info.filename
            need(target.resolve().is_relative_to(dest),"Extraction target escapes destination")
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open("xb") as f:
                f.write(z.read(info))
    need(all(digest((dest/n).read_bytes())==r["sha256"] for n,r in manifest["files"].items()),"Restored hash differs")
    # Empty private work area is a runtime prerequisite, never a ZIP payload.
    (dest/"tmp").mkdir()
    return {"restored_to":str(dest),"payload_files":len(manifest["files"]),"hashes_verified":True}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=["build","verify","restore"])
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--receipt",type=Path)
    p.add_argument("--dest",type=Path)
    args=p.parse_args()
    try:
        archive=args.archive.resolve()
        expected=decode(args.receipt.read_bytes())["sha256"] if args.receipt else None
        if args.action=="build":
            need(args.dest is None and args.receipt is None,"Build has no dest/receipt input")
            result=build(archive)
        elif args.action=="verify":
            need(args.dest is None,"Verify has no destination")
            m=verify(archive,expected);result={"verified":True,"payload_files":len(m["files"])}
        else:
            need(args.dest is not None,"Restore requires --dest")
            result=restore(archive,args.dest.resolve(),expected)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,OSError,KeyError,TypeError,UnicodeError,zipfile.BadZipFile) as exc:
        print("Ошибка пакета:",str(exc)[:200])
        return 2


if __name__=="__main__":
    raise SystemExit(main())
