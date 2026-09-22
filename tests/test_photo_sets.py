import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import photo_sets as sets


def upload(images=2, name='テスト', data=None):
    if data is None:
        stream=io.BytesIO();Image.new('RGB',(16,16),'red').save(stream,format='PNG')
        data=stream.getvalue()
    body=b'--test\r\nContent-Disposition: form-data; name="name"\r\n\r\n'+name.encode()+b'\r\n'
    for _ in range(images):
        body+=b'--test\r\nContent-Disposition: form-data; name="files"; filename="../../bad.png"\r\nContent-Type: image/png\r\n\r\n'+data+b'\r\n'
    return 'multipart/form-data; boundary=test',body+b'--test--\r\n'


class PhotoSetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name)
        for key,value in [('STORE',base/'uploads'),('TRASH',base/'trash')]:
            patcher=patch.object(sets,key,value);patcher.start();self.addCleanup(patcher.stop)

    def test_upload_ignores_client_filename_and_archive_keeps_bytes(self):
        meta=sets.create(*upload());folder=sets.folder(meta['id'])
        self.assertEqual(meta['images'],['img_000.png','img_001.png'])
        contents=(folder/'input/img_000.png').read_bytes()
        sets.archive(meta['id'])
        self.assertEqual(sets.listing(),[])
        archived=next(sets.TRASH.glob('*/input/img_000.png'))
        self.assertEqual(archived.read_bytes(),contents)

    def test_rejects_wrong_photo_counts_and_paths(self):
        for count in (1,9):
            with self.assertRaises(sets.InputError):sets.create(*upload(images=count))
        with self.assertRaises(sets.InputError):sets.folder('../outputs')
        self.assertEqual(sets.listing(),[])

    def test_active_job_cannot_be_archived(self):
        meta=sets.create(*upload());sets.ACTIVE.add(meta['id'])
        try:
            with self.assertRaises(sets.InputError):sets.archive(meta['id'])
            self.assertTrue(sets.folder(meta['id']).exists())
        finally:sets.ACTIVE.discard(meta['id'])

    def test_interrupted_generation_retains_previous_result(self):
        meta=sets.create(*upload());path=sets.folder(meta['id'])
        meta.update(status='running',result='runs/previous',has_ply=True)
        sets.write_meta(path,meta);sets.recover_jobs()
        recovered=sets.get(meta['id'])
        self.assertEqual(recovered['status'],'error')
        self.assertEqual(recovered['result'],'runs/previous')
        self.assertTrue(recovered['has_ply'])

    def test_invalid_image_does_not_create_set(self):
        content_type,body=upload()
        body=body.replace(b'\x89PNG',b'BAD!')
        with self.assertRaises(sets.InputError):sets.create(content_type,body)
        self.assertEqual(sets.listing(),[])

    def test_mpo_upload_uses_primary_image_and_corrects_orientation(self):
        source = Image.new('RGB', (1152, 1536), 'red')
        auxiliary = Image.new('RGB', (32, 24), 'blue')
        exif = source.getexif()
        exif[274] = 6
        stream = io.BytesIO()
        source.save(stream, format='MPO', save_all=True,
                    append_images=[auxiliary], exif=exif)
        with Image.open(io.BytesIO(stream.getvalue())) as original:
            self.assertEqual(original.format, 'MPO')
            self.assertEqual(original.n_frames, 2)
        meta = sets.create(*upload(images=4, data=stream.getvalue()))
        self.assertEqual(meta['images'], [f'img_{i:03}.jpg' for i in range(4)])
        for name in meta['images']:
            with Image.open(sets.folder(meta['id'])/'input'/name) as saved:
                self.assertEqual(saved.format, 'JPEG')
                self.assertEqual(saved.size, (1536, 1152))
                self.assertIn(saved.getexif().get(274), (None, 1))
                red, green, blue = saved.getpixel((100, 100))
                self.assertGreater(red, 240)
                self.assertLess(blue, 10)

    def test_heic_upload_converts_four_photos_to_full_size_jpeg(self):
        source = Image.new('RGB', (1152, 1536), 'red')
        stream = io.BytesIO()
        source.save(stream, format='HEIF')
        meta = sets.create(*upload(images=4, data=stream.getvalue()))
        folder = sets.folder(meta['id'])
        self.assertEqual(meta['images'], [f'img_{i:03}.jpg' for i in range(4)])
        for name in meta['images']:
            with Image.open(folder/'input'/name) as saved:
                self.assertEqual(saved.format, 'JPEG')
                self.assertEqual(saved.size, source.size)
                saved.load()


if __name__=='__main__':unittest.main()
