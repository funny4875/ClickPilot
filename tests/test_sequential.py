import json
import unittest
from unittest.mock import Mock
import script_engine as engine

class SequentialTests(unittest.TestCase):
    def parse(self, steps):
        return engine.parse_script('\n'.join(map(json.dumps, steps)))

    def test_inputs_and_forward_reference(self):
        steps=self.parse([{'action':'set','into':'name','value':'${USER}'},{'action':'send_keys','xpath':'//input','value':'${name}'}])
        self.assertEqual(engine.required_inputs(steps), ['USER'])
        with self.assertRaisesRegex(ValueError,'第 2 行'):
            engine.required_inputs(list(reversed(steps)))

    def test_single_pass_and_missing_variable(self):
        self.assertEqual(engine.resolve_text('${a}',{'a':'${b}','b':'secret'}),'${b}')
        with self.assertRaisesRegex(ValueError,'missing'):
            engine.resolve_text('${missing}',{})

    def test_validation(self):
        for step in [{'action':'ocr','xpath':'//img','into':'bad name'}, {'action':'set','into':'ok','value':3}, {'action':'read_attribute','xpath':'//a','into':'link'}]:
            with self.assertRaises(ValueError): self.parse([step])

    def test_ocr_empty_and_case(self):
        recognizer=engine.ImageRecognizer(); recognizer.engine=Mock()
        recognizer.engine.classification.return_value=' ab12 '
        self.assertEqual(recognizer.recognize(b'png','upper'),'AB12')
        recognizer.engine.classification.return_value=' '
        with self.assertRaisesRegex(ValueError,'未辨識'): recognizer.recognize(b'png')
