import importlib.util,io,json,tarfile,tempfile,unittest
from pathlib import Path
p=Path(__file__).with_name('replay.py');spec=importlib.util.spec_from_file_location('producer_source_replay',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def archive_member(name,kind=tarfile.REGTYPE,data=b'x'):
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as t:
        info=tarfile.TarInfo(name);info.type=kind
        if kind==tarfile.SYMTYPE:info.linkname='../../escape';info.size=0;t.addfile(info)
        else:info.size=len(data);t.addfile(info,io.BytesIO(data))
    return buf.getvalue()


class SourceReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((m.HERE/'source_manifest.json').read_bytes())
        cls.base,cls.target=m.validate_manifest(cls.manifest)
        cls.patch=(m.HERE/'v5_changes.patch').read_bytes()
    def test_full_offline_reconstruction(self):
        result=m.replay();self.assertEqual((result['base_files'],result['changed_files'],result['reconstructed_files']),(68,16,76))
        self.assertEqual(result['installed_build_identity'],'NOT_ESTABLISHED')
    def test_archive_path_traversal_or_unexpected_file(self):
        for name in ('../escape','/absolute','libtorch/../escape','libtorch/src/unexpected.cpp'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as d,self.assertRaises(ValueError):
                m.extract_base(archive_member(name),self.base,Path(d))
    def test_archive_link_rejected(self):
        with tempfile.TemporaryDirectory() as d,self.assertRaisesRegex(ValueError,'nonregular'):
            m.extract_base(archive_member('libtorch/CMakeLists.txt',tarfile.SYMTYPE),self.base,Path(d))
    def test_rehashed_patch_path_and_mode_mutations(self):
        bad=self.patch.replace(b'a/libtorch/CMakeLists.txt b/libtorch/CMakeLists.txt',b'a/libtorch/../escape b/libtorch/../escape',1)
        m.sha(bad)
        with self.assertRaisesRegex(ValueError,'unsafe path'):m.validate_patch(bad,self.base,self.target)
        bad=self.patch.replace(b'new file mode 100644',b'new file mode 120000',1)
        with self.assertRaisesRegex(ValueError,'file mode'):m.validate_patch(bad,self.base,self.target)
    def test_manifest_and_file_content_mutations(self):
        d=json.loads(json.dumps(self.manifest));del d['target_file_sha256']['libtorch/CMakeLists.txt']
        with self.assertRaisesRegex(ValueError,'file counts'):m.validate_manifest(d)
        fake=archive_member('libtorch/CMakeLists.txt',data=b'incorrect')
        with tempfile.TemporaryDirectory() as t,self.assertRaisesRegex(ValueError,'base source SHA'):
            m.extract_base(fake,self.base,Path(t))

if __name__=='__main__':unittest.main()
