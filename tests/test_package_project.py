"""Archive boundary tests; no model/primary source or benchmark calls."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import package_project as pkg


class PackageTests(unittest.TestCase):
    def setUp(self):
        parent=ROOT/"tmp/package-tests";parent.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=parent)
        self.folder=Path(self.tmp.name).resolve()
        assert self.folder.is_relative_to(parent.resolve())
        self.addCleanup(self.tmp.cleanup)

    def archive(self,override=None,extra=None,corrupt_hash=False):
        data={pkg.LIST:json.dumps([pkg.LIST,"README.md"]).encode(),"README.md":b"Own unit-test README\n"}
        manifest={"format":pkg.FORMAT,"files":{n:{"bytes":len(b),"sha256":pkg.digest(b)} for n,b in data.items()}}
        if corrupt_hash:manifest["files"]["README.md"]["sha256"]="0"*64
        data[pkg.MANIFEST]=json.dumps(manifest).encode()
        archive=self.folder/"fixture.zip"
        with zipfile.ZipFile(archive,"x") as z:
            for n,b in data.items():z.writestr(n,b)
            if override:z.writestr(override,b"untrusted extra payload")
            if extra:z.writestr(extra,b"unit test symlink target")
        return archive

    def test_valid_archive_and_restore(self):
        p=self.archive();self.assertEqual(len(pkg.verify(p)["files"]),2)
        dest=self.folder/"new-root"
        self.assertTrue(pkg.restore(p,dest)["hashes_verified"])
        self.assertTrue((dest/"tmp").is_dir())
        self.assertEqual((dest/"README.md").read_bytes(),b"Own unit-test README\n")

    def test_traversal_rejected_before_writing(self):
        p=self.archive(override="../escape.py");dest=self.folder/"new-root"
        with self.assertRaises(ValueError):pkg.restore(p,dest)
        self.assertFalse(dest.exists())

    def test_windows_and_private_paths(self):
        for name in ["C:/escape.py","/abs.py","a\\x.py","a//x.py","a/./x.py","a/../x.py","tmp/x.py",".env",".env.local.py","a/NUL.txt","a/file.py.","a/file.py ","data/raw/x.json","data/private/x.json"]:
            with self.subTest(name=name),self.assertRaises(ValueError):pkg.permitted(name)

    def test_pdf_weights_and_keys_rejected(self):
        for name in ["report.pdf","model.gguf","index.sqlite","secret.pem","page.png","program.exe"]:
            with self.subTest(name=name),self.assertRaises(ValueError):pkg.permitted(name)

    def test_extra_member_rejected(self):
        with self.assertRaises(ValueError):pkg.verify(self.archive(override="extra.py"))

    def test_hash_tampering_rejected(self):
        with self.assertRaises(ValueError):pkg.verify(self.archive(corrupt_hash=True))

    def test_case_collision_rejected(self):
        with self.assertRaises(ValueError):pkg.verify(self.archive(override="readme.md"))

    def test_duplicate_member_rejected(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore",UserWarning)
            p=self.archive(override="README.md")
        with self.assertRaises(ValueError):pkg.verify(p)

    def test_symlink_rejected(self):
        info=zipfile.ZipInfo("link.py");info.create_system=3;info.external_attr=0o120777<<16
        with self.assertRaises(ValueError):pkg.verify(self.archive(extra=info))

    def test_receipt_hash_mismatch(self):
        with self.assertRaises(ValueError):pkg.verify(self.archive(),"0"*64)

    def test_no_restore_over_existing_folder(self):
        with self.assertRaises(ValueError):pkg.restore(self.archive(),self.folder)

    def test_no_restore_outside_tmp(self):
        with self.assertRaises(ValueError):pkg.restore(self.archive(),ROOT/"output/forbidden-restore")


if __name__=="__main__":
    unittest.main()
