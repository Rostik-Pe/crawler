import asynctest
import aiohttp
from unittest.mock import patch, AsyncMock
import json
from .github_crawler import GitHubCrawler, main


class TestGitHubCrawler(asynctest.TestCase):
    def setUp(self):
        self.input_data = {
            "keywords": ["python", "asyncio"],
            "proxies": ["194.126.37.94:8080"],
            "type": "Repositories"
        }
        self.crawler = GitHubCrawler(self.input_data)

    def test_init(self):
        self.assertEqual(self.crawler.keywords, ["python", "asyncio"])
        self.assertEqual(self.crawler.proxies, ["194.126.37.94:8080"])
        self.assertEqual(self.crawler.search_type, "Repositories")

    def test_get_random_proxy(self):
        proxy = self.crawler.get_random_proxy()
        self.assertIn(proxy, self.input_data["proxies"])

    def test_create_search_url(self):
        expected_url = "https://github.com/search?q=python+asyncio&type=repositories"
        self.assertEqual(self.crawler.create_search_url(), expected_url)

    @asynctest.patch('aiohttp.ClientSession.get')
    async def test_make_request(self, mock_get):
        mock_response = AsyncMock()
        mock_response.text.return_value = "test content"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value.__aenter__.return_value = mock_response

        async with aiohttp.ClientSession() as session:
            content = await self.crawler.make_request(session, "https://test.com")
        self.assertEqual(content, "test content")

    @asynctest.patch('aiohttp.ClientSession.get')
    async def test_make_request_error(self, mock_get):
        mock_get.side_effect = aiohttp.ClientError("Test error")

        async with aiohttp.ClientSession() as session:
            content = await self.crawler.make_request(session, "https://test.com")
        self.assertIsNone(content)

    async def test_parse_html_repositories(self):
        html_content = """
        <div class="repo-list">
            <div class="repo-list-item">
                <a class="v-align-middle" href="/user/repo">Repo Name</a>
            </div>
        </div>
        """
        self.crawler.search_type = "Repositories"

        async def mock_get_repo_extra_info(*args):
            return {"owner": "user", "language_stats": {}}

        with patch.object(self.crawler, 'get_repo_extra_info', new=mock_get_repo_extra_info):
            async with aiohttp.ClientSession() as session:
                results = await self.crawler.parse_html(session, html_content)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['url'], "https://github.com/user/repo")
        self.assertEqual(results[0]['extra']['owner'], "user")

    async def test_parse_html_issues(self):
        html_content = """
        <div class="issue-list">
            <div class="issue-list-item">
                <a class="Link--primary" href="/user/repo/issues/1">Issue Title</a>
            </div>
        </div>
        """
        self.crawler.search_type = "Issues"

        async with aiohttp.ClientSession() as session:
            results = await self.crawler.parse_html(session, html_content)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['url'], "https://github.com/user/repo/issues/1")

    async def test_parse_html_invalid(self):
        with self.assertRaises(ValueError):
            async with aiohttp.ClientSession() as session:
                await self.crawler.parse_html(session, None)

    @asynctest.patch('aiohttp.ClientSession.get')
    async def test_get_repo_extra_info(self, mock_get):
        html_content = """
        <div class="repository-lang-stats-graph">
            <span class="language-color" aria-label="Python 60.0%"></span>
            <span class="language-color" aria-label="JavaScript 40.0%"></span>
        </div>
        """
        mock_response = AsyncMock()
        mock_response.text.return_value = html_content
        mock_response.raise_for_status.return_value = None
        mock_get.return_value.__aenter__.return_value = mock_response

        async with aiohttp.ClientSession() as session:
            info = await self.crawler.get_repo_extra_info(session, "https://github.com/user/repo")

        self.assertEqual(info['owner'], "user")
        self.assertEqual(info['language_stats'], {"Python": 60.0, "JavaScript": 40.0})

    @asynctest.patch.object(GitHubCrawler, 'make_request')
    @asynctest.patch.object(GitHubCrawler, 'parse_html')
    async def test_crawl(self, mock_parse_html, mock_make_request):
        mock_make_request.return_value = "html content"
        mock_parse_html.return_value = [
            {"url": "https://github.com/user/repo", "extra": {"owner": "user", "language_stats": {}}}]

        results = await self.crawler.crawl()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['url'], "https://github.com/user/repo")
        self.assertEqual(results[0]['extra']['owner'], "user")

    @asynctest.patch.object(GitHubCrawler, 'make_request')
    async def test_crawl_error(self, mock_make_request):
        mock_make_request.return_value = None

        with self.assertRaises(RuntimeError):
            await self.crawler.crawl()

    @asynctest.patch.object(GitHubCrawler, 'crawl')
    async def test_main_function_crawler(self, mock_crawl):
        mock_crawl.return_value = [
            {
                "url": "https://github.com/user/repo",
                "extra": {
                    "owner": "user",
                    "language_stats": {
                        "Python": 60.0,
                        "JavaScript": 40.0
                    }
                }
            }
        ]

        input_data = {
            "keywords": ["python"],
            "proxies": ["194.126.37.94:8080"],
            "type": "Repositories"
        }
        input_json = json.dumps(input_data)

        result = await main(input_json)
        result_list = json.loads(result)

        self.assertEqual(len(result_list), 1)
        self.assertEqual(result_list[0]['url'], "https://github.com/user/repo")
        self.assertEqual(result_list[0]['extra']['owner'], "user")
        self.assertEqual(result_list[0]['extra']['language_stats']['Python'], 60.0)

    async def test_main_function_specific_results(self):
        input_data = [
            {
                "url": "https://github.com/user/repo",
                "extra": {
                    "owner": "user",
                    "language_stats": {
                        "Python": 60.0,
                        "JavaScript": 40.0
                    }
                }
            }
        ]
        input_json = json.dumps(input_data)

        result = await main(input_json)
        result_list = json.loads(result)

        self.assertEqual(len(result_list), 1)
        self.assertEqual(result_list[0]['url'], "https://github.com/user/repo")
        self.assertEqual(result_list[0]['extra']['owner'], "user")
        self.assertEqual(result_list[0]['extra']['language_stats']['Python'], 60.0)

    async def test_main_function_error(self):
        input_json = "invalid json"

        result = await main(input_json)
        result_dict = json.loads(result)

        self.assertIn("error", result_dict)
        self.assertIn("Invalid input JSON", result_dict["error"])


if __name__ == "__main__":
    asynctest.main()
