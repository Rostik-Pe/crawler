import asyncio
import json
import os
import unittest
from unittest.mock import patch, AsyncMock, mock_open

import aiohttp
from bs4 import BeautifulSoup
from parameterized import parameterized

from github_crawler import GitHubCrawler, main, generate_input_data_json


class TestGitHubCrawler(unittest.TestCase):

    def setUp(self):
        self.input_data = {
            "keywords": ["python", "asyncio"],
            "proxies": ["194.126.37.94:8080", "13.78.125.167:8080"],
            "type": "Repositories"
        }
        self.crawler = GitHubCrawler(self.input_data)

    def test_init(self):
        self.assertEqual(self.crawler.keywords, ["python", "asyncio"])
        self.assertEqual(self.crawler.proxies, ["194.126.37.94:8080", "13.78.125.167:8080"])
        self.assertEqual(self.crawler.search_type, "Repositories")
        self.assertEqual(self.crawler.base_url, 'https://github.com/search')
        self.assertEqual(self.crawler.delay, 0.5)
        self.assertEqual(self.crawler.timeout, 10)

    def test_get_random_proxy(self):
        proxy = self.crawler.get_random_proxy()
        self.assertIn(proxy, self.crawler.proxies)

        crawler_no_proxy = GitHubCrawler({"keywords": [], "proxies": [], "type": "Repositories"})
        self.assertIsNone(crawler_no_proxy.get_random_proxy())

    @parameterized.expand([
        (["python", "asyncio"], "Repositories", "https://github.com/search?q=python+asyncio&type=repositories"),
        (["machine learning", "python"], "Repositories",
         "https://github.com/search?q=machine learning+python&type=repositories"),
        (["python", "asyncio"], "Issues", "https://github.com/search?q=python+asyncio&type=issues"),
    ])
    def test_create_search_url(self, keywords, search_type, expected_url):
        self.crawler.keywords = keywords
        self.crawler.search_type = search_type
        url = self.crawler.create_search_url()
        self.assertEqual(url, expected_url)

    def test_validate_html(self):
        with self.assertRaises(ValueError):
            GitHubCrawler.validate_html("")
        with self.assertRaises(ValueError):
            GitHubCrawler.validate_html(123)
        GitHubCrawler.validate_html("<html></html>")
        GitHubCrawler.validate_html("<html><body>Content</body></html>")

    def test_create_soup(self):
        html = "<html><body><p>Test</p></body></html>"
        soup = GitHubCrawler.create_soup(html)
        self.assertIsInstance(soup, BeautifulSoup)
        self.assertIsNotNone(soup.find('p'))

        with self.assertRaises(ValueError):
            GitHubCrawler.create_soup(None)
        with self.assertRaises(ValueError):
            GitHubCrawler.create_soup(123)

    def test_find_language_div(self):
        html = '''
        <html>
            <div class="BorderGrid-row"><p>First</p></div>
            <div class="BorderGrid-row"><p>Second</p></div>
        </html>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        div = GitHubCrawler.find_language_div(soup)
        self.assertEqual(div.find('p').text, "Second")

        html_no_div = '<html></html>'
        soup_no_div = BeautifulSoup(html_no_div, 'html.parser')
        self.assertIsNone(GitHubCrawler.find_language_div(soup_no_div))

    def test_extract_language_info(self):
        html = '<li><span class="text-bold">Python</span><span>80%</span></li>'
        li = BeautifulSoup(html, 'html.parser').find('li')
        language, percentage = GitHubCrawler.extract_language_info(li)
        self.assertEqual((language, percentage), ("Python", "80%"))

        html_no_percentage = '<li><span class="text-bold">Python</span></li>'
        li_no_percentage = BeautifulSoup(html_no_percentage, 'html.parser').find('li')
        language, percentage = GitHubCrawler.extract_language_info(li_no_percentage)
        self.assertEqual((language, percentage), ("Python", None))

        html_invalid = '<li><span>Invalid</span></li>'
        li_invalid = BeautifulSoup(html_invalid, 'html.parser').find('li')
        self.assertEqual(GitHubCrawler.extract_language_info(li_invalid), (None, None))

    @patch('aiohttp.ClientSession')
    async def test_make_request(self, mock_session):
        scenarios = [
            ("Test content", "Test content"),
            (aiohttp.ClientError(), None),
            (asyncio.TimeoutError(), None),
            ("", None)
        ]

        for scenario, expected_result in scenarios:
            if isinstance(scenario, str):
                mock_response = AsyncMock()
                mock_response.text.return_value = scenario
                mock_response.__aenter__.return_value = mock_response
                mock_session.return_value.get.return_value = mock_response
            else:
                mock_session.return_value.get.side_effect = scenario

            content = await self.crawler.make_request(mock_session(), "https://test.com")
            self.assertEqual(content, expected_result)

    async def test_parse_html(self):
        html = '''
        <html>
            <div class="BorderGrid-row">
                <li><span class="text-bold">Python</span><span>80%</span></li>
                <li><span class="text-bold">JavaScript</span><span>20%</span></li>
            </div>
        </html>
        '''
        result = await self.crawler.parse_html(html)
        self.assertEqual(result, {"language_stats": {"Python": "80%", "JavaScript": "20%"}})

        with self.assertRaises(ValueError):
            await self.crawler.parse_html("")

    @patch('aiohttp.ClientSession')
    async def test_process_single_repository(self, mock_session):
        scenarios = [
            ('''
            <html>
                <div class="BorderGrid-row">
                    <li><span class="text-bold">Python</span><span>100%</span></li>
                </div>
            </html>
            ''', {
                'url': 'https://github.com/test/repo/',
                'extra': {
                    'owner': 'test',
                    'language_stats': {'Python': '100%'}
                }
            }),
            (aiohttp.ClientError(), None),
            ("<html></html>", None)
        ]

        for html_content, expected_result in scenarios:
            if isinstance(html_content, str):
                mock_response = AsyncMock()
                mock_response.text.return_value = html_content
                mock_response.__aenter__.return_value = mock_response
                mock_session.return_value.get.return_value = mock_response
            else:
                mock_session.return_value.get.side_effect = html_content

            repo = {"owner": "test", "repo_name": "repo"}
            result = await self.crawler.process_single_repository(mock_session(), repo)
            self.assertEqual(result, expected_result)

    @patch('aiohttp.ClientSession')
    async def test_crawl(self, mock_session):
        mock_response = AsyncMock()
        mock_response.text.return_value = json.dumps({
            'payload': {
                'results': [
                    {'repo': {'repository': {'owner_login': 'test', 'name': 'repo'}}}
                ]
            }
        })
        mock_response.__aenter__.return_value = mock_response
        mock_session.return_value.get.return_value = mock_response

        with patch.object(self.crawler, 'process_repositories',
                          return_value=[{'url': 'https://github.com/test/repo/'}]):
            with patch.object(self.crawler, 'save'):
                await self.crawler.crawl()
                self.crawler.save.assert_called_once()

    def test_extract_repositories(self):
        content_empty = json.dumps({'payload': {'results': []}})
        repos_empty = self.crawler.extract_repositories(content_empty)
        self.assertEqual(repos_empty, [])

        content_multiple = json.dumps({
            'payload': {
                'results': [
                    {'repo': {'repository': {'owner_login': 'user1', 'name': 'repo1'}}},
                    {'repo': {'repository': {'owner_login': 'user2', 'name': 'repo2'}}}
                ]
            }
        })
        repos_multiple = self.crawler.extract_repositories(content_multiple)
        expected = [
            {'owner': 'user1', 'repo_name': 'repo1'},
            {'owner': 'user2', 'repo_name': 'repo2'}
        ]
        self.assertEqual(repos_multiple, expected)

    @patch('github_crawler.os.makedirs')
    @patch('github_crawler.datetime')
    def test_save(self, mock_datetime, mock_makedirs):
        data = [{"test": "data"}]
        mock_datetime.now.return_value.strftime.return_value = "2023_01_01_00_00_00"

        mock_file = mock_open()
        with patch('github_crawler.open', mock_file):
            self.crawler.save(data)

        expected_path = os.path.join('output_results', '2023_01_01_00_00_00_items.json')
        mock_file.assert_called_once_with(expected_path, 'w')

        expected_json = json.dumps(data, indent=4)
        actual_calls = mock_file().write.call_args_list
        actual_json = ''.join(call.args[0] for call in actual_calls)

        self.assertEqual(expected_json, actual_json)

        mock_makedirs.assert_called_once_with('output_results', exist_ok=True)


class TestMainFunction(unittest.TestCase):

    @patch('github_crawler.GitHubCrawler.crawl')
    async def test_main(self, mock_crawl):
        scenarios = [
            (json.dumps({
                "keywords": ["python"],
                "proxies": ["194.126.37.94:8080"],
                "type": "Repositories"
            }), "[]"),
            (json.dumps([{"url": "https://github.com/test/repo"}]),
             json.dumps([{"url": "https://github.com/test/repo"}], indent=2)),
            ("invalid json", json.dumps({"error": "Invalid input JSON"})),
            ("{}", json.dumps({"error": "Invalid input format"})),
        ]

        for input_json, expected_output in scenarios:
            result = await main(input_json)
            self.assertEqual(result, expected_output)

        mock_crawl.side_effect = Exception("Crawl error")
        result = await main(json.dumps({
            "keywords": ["python"],
            "proxies": ["194.126.37.94:8080"],
            "type": "Repositories"
        }))
        self.assertIn("error", json.loads(result))


class TestGenerateInputDataJson(unittest.TestCase):

    @parameterized.expand([
        ("python asyncio", "Repositories", ['python', 'asyncio'], "Repositories"),
        ("python", "Issues", ['python'], "Issues"),
        ("", "Repositories", [], "Repositories"),
        ("python django rest", "Issues", ["python", "django", "rest"], "Issues"),
    ])
    def test_generate_input_data_json(self, input_key, input_type, expected_keywords, expected_type):
        result = generate_input_data_json(input_key, input_type)
        data = json.loads(result)
        self.assertEqual(data['keywords'], expected_keywords)
        self.assertEqual(data['type'], expected_type)
        self.assertEqual(data['proxies'], ["194.126.37.94:8080", "13.78.125.167:8080"])


if __name__ == '__main__':
    unittest.main()
