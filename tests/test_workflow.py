import unittest
from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / '.github/workflows/review.yml'


class WorkflowTests(unittest.TestCase):
    def test_scheduled_review_uses_private_workspace_and_gpt(self):
        text = WORKFLOW.read_text()
        command = next(line for line in text.splitlines()
                       if 'python -m pepper automate' in line)
        for flag in ('--research-sheets', '--publish-research-sheets', '--llm', '--drive-folder'):
            self.assertIn(flag, command)
        self.assertNotIn(' --sheets ', command)
        self.assertNotIn('--publish-sheets', command)
        self.assertIn("'OPENAI_API_KEY'", text)
        self.assertIn("'OPENAI_MODEL'", text)

    def test_raw_google_credential_is_scoped_to_prepare_step(self):
        text = WORKFLOW.read_text()
        before, after = text.split('- name: Prepare private credentials', 1)
        self.assertNotIn('GOOGLE_CREDENTIALS_JSON:', before)
        self.assertIn('GOOGLE_CREDENTIALS_JSON: ${{ secrets.GOOGLE_CREDENTIALS_JSON }}', after)
        self.assertIn('GOOGLE_APPLICATION_CREDENTIALS=', after)


if __name__ == '__main__':
    unittest.main()
