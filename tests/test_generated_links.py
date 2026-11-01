import unittest
from fastapi import HTTPException
from generated_links import describe_url,upsert,validate_library
class GeneratedLinkTests(unittest.TestCase):
 def test_nsp_segment_metadata(self):
  r=describe_url('https://pborovicka72-dotcom.github.io/eduvize-svatky/index.html?viewMode=nsp&segment_orientation=portrait&segment_style=4&segment_block=2')
  self.assertEqual((r['app'],r['output'],r['orientation'],r['style'],r['segment']),('holidays','nsp','portrait',4,2))
 def test_web_and_kiosk_are_not_mislabeled_as_nsp(self):
  for mode in ['web','kiosk']:
   r=describe_url('https://eduvize-jidelnicek.onrender.com/index.html?viewMode='+mode+'&presentation=day&canteen=11592');self.assertEqual(r['output'],mode);self.assertIsNone(r['style']);self.assertIn('11592',r['details'])
  self.assertEqual(describe_url('https://pborovicka72-dotcom.github.io/eduvize-kiosek/index.html?config=abc')['output'],'kiosk')
 def test_duplicate_updates_preserve_label_and_creation_date(self):
  url='https://eduvize-weather.onrender.com/display?viewMode=nsp&segment_style=2&segment_block=1&v=1'
  items,first=upsert([],url,'Vchod','2026-11-01T10:00:00+00:00','first');items,last=upsert(items,url.replace('v=1','v=2'),'','2026-11-01T11:00:00+00:00','second')
  self.assertEqual(len(items),1);self.assertEqual(last['label'],'Vchod');self.assertEqual(last['createdAt'],first['createdAt']);self.assertEqual(last['copies'],2)
  same,item=upsert(items,last['url'],capture_id='second');self.assertEqual(item['copies'],2)
 def test_untrusted_or_admin_urls_are_rejected(self):
  for url in ['javascript:alert(1)','https://example.org/','https://eduvize-jidelnicek.onrender.com/config.html','https://eduvize-aktuality.onrender.com/?token=x','https://eduvize-weather.onrender.com/display#edu-auth-code=x','https://user:pass@eduvize-weather.onrender.com/display']:
   with self.subTest(url=url),self.assertRaises(HTTPException):describe_url(url)
 def test_forged_record_identity_is_rejected(self):
  items,item=upsert([],'https://eduvize-jidelnicek.onrender.com/index.html?viewMode=web');self.assertIs(validate_library({'items':items})['items'],items);items[0]['id']='forged'
  with self.assertRaises(HTTPException):validate_library({'items':items})
if __name__=='__main__':unittest.main()
