import random
import asyncio
import aiohttp
import json
from bs4 import BeautifulSoup
import logging
from typing import List, Dict, Optional, Any
import unittest

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class GitHubCrawler:
    """
    GitHubCrawler class for crawling GitHub search results.

    This class implements a crawler that searches GitHub based on given keywords,
    uses proxies for requests, and supports different types of GitHub objects.

    Attributes:
        keywords (List[str]): List of keywords to search on GitHub.
        proxies (List[str]): List of proxies to use for HTTP requests.
        search_type (str): Type of GitHub objects to search (Repositories, Issues, Wikis).
        base_url (str): Base URL for GitHub search.

    Usage:
        input_data = {
            "keywords": ["python", "asyncio"],
            "proxies": ["194.126.37.94:8080", "13.78.125.167:8080"],
            "type": "Repositories"
        }
        crawler = GitHubCrawler(input_data)
        results = await crawler.crawl()
    """

    def __init__(self, input_data: Dict[str, Any]):
        """
        Initialize GitHubCrawler with input data.

        Args:
            input_data (Dict[str, Any]): Dictionary containing 'keywords', 'proxies', and 'type'.
        """
        logging.info(f"Initializing GitHubCrawler with input data: {input_data}")
        self.keywords: List[str] = input_data['keywords']
        self.proxies: List[str] = input_data['proxies']
        self.search_type: str = input_data['type']
        self.base_url: str = 'https://github.com/search'

    def get_random_proxy(self) -> Optional[str]:
        """
        Get a random proxy from the list of proxies.

        Returns:
            Optional[str]: Randomly selected proxy in the format 'host:port', or None if no proxies are available.
        """
        proxy = random.choice(self.proxies) if self.proxies else None
        logging.info(f"Selected proxy: {proxy}")
        return proxy

    def create_search_url(self) -> str:
        """
        Create the GitHub search URL based on keywords and search type.

        Returns:
            str: Generated search URL.
        """
        query = '+'.join(self.keywords)
        search_url = f"{self.base_url}?q={query}&type={self.search_type.lower()}"
        logging.info(f"Generated search URL: {search_url}")
        return search_url

    async def make_request(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """
        Make an asynchronous HTTP GET request using aiohttp session.

        Args:
            session (aiohttp.ClientSession): Aiohttp client session object.
            url (str): URL to make the GET request.

        Returns:
            Optional[str]: Response content as text, or None if request fails.

        Raises:
            aiohttp.ClientError: If there's an error with the HTTP request.
            asyncio.TimeoutError: If the request times out.
        """
        proxy = self.get_random_proxy()
        proxies = {'http': f'http://{proxy}', 'https': f'https://{proxy}'} if proxy else None
        logging.info(f"Making request to {url} using proxies: {proxies}")
        try:
            async with session.get(url, proxy=proxies, timeout=10) as response:
                response.raise_for_status()
                content = await response.text()
                if not content.strip():
                    logging.warning("Received empty content from server")
                    return
                return content
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logging.error(f"Error making request: {e}")
            return
        except Exception as e:
            logging.error(f"Unexpected error in make_request: {e}")
            return
        finally:
            await asyncio.sleep(0.5)  # delay between requests

    async def parse_html(self, session: aiohttp.ClientSession, html: str) -> List[Dict[str, Any]]:
        """
        Parse HTML content asynchronously using BeautifulSoup.

        Args:
            session (aiohttp.ClientSession): Aiohttp client session object.
            html (str): HTML content to parse.

        Returns:
            List[Dict[str, Any]]: List of dictionaries containing parsed results.

        Raises:
            ValueError: If the HTML content is invalid.
        """
        if not isinstance(html, str):
            logging.error(f"Invalid HTML content type: {type(html)}")
            raise ValueError(f"Invalid HTML content type: {type(html)}. Expected str.")

        if not html.strip():
            logging.warning("Empty HTML content")
            return []

        try:
            soup = BeautifulSoup(html, 'html.parser', from_encoding='utf-8')
        except Exception as e:
            logging.error(f"Error creating BeautifulSoup object: {e}")
            raise ValueError(f"Error parsing HTML: {e}")

        async def get_results():
            if self.search_type.lower() == 'repositories':
                for repo in soup.select('.repo-list-item'):
                    link = repo.select_one('a.v-align-middle')
                    if link:
                        url = f"https://github.com{link['href']}"
                        extra_info = await self.get_repo_extra_info(session, url)
                        yield {"url": url, "extra": extra_info}
            elif self.search_type.lower() in ['issues', 'wikis']:
                for item in soup.select('.issue-list-item, .wiki-list-item'):
                    link = item.select_one('a.Link--primary')
                    if link:
                        yield {"url": f"https://github.com{link['href']}"}

        return [result async for result in get_results()]

    async def get_repo_extra_info(self, session: aiohttp.ClientSession, repo_url: str) -> Dict[str, Any]:
        """
        Get additional repository information asynchronously.

        Args:
            session (aiohttp.ClientSession): Aiohttp client session object.
            repo_url (str): URL of the repository to fetch extra information.

        Returns:
            Dict[str, Any]: Dictionary containing additional repository information.
        """
        html = await self.make_request(session, repo_url)
        if not html:
            return {}

        try:
            soup = BeautifulSoup(html, 'html.parser', from_encoding='utf-8')
        except Exception as e:
            logging.error(f"Error creating BeautifulSoup object for repo info: {e}")
            return {}

        owner = repo_url.split('/')[-2]

        language_stats = {}
        lang_stats_bar = soup.select_one('.repository-lang-stats-graph')
        if lang_stats_bar:
            for lang in lang_stats_bar.select('.language-color'):
                lang_name = lang.get('aria-label', '').split()[0]
                lang_percent = float(lang.get('aria-label', '').split()[-1].rstrip('%'))
                language_stats[lang_name] = lang_percent

        return {
            "owner": owner,
            "language_stats": language_stats
        }

    async def crawl(self) -> List[Dict[str, Any]]:
        """
        Perform crawling of GitHub search results asynchronously.

        Returns:
            List[Dict[str, Any]]: List of dictionaries containing parsed search results.

        Raises:
            RuntimeError: If failed to retrieve HTML content.
        """
        url = self.create_search_url()
        logging.info(f"Crawling URL: {url}")

        async with aiohttp.ClientSession() as session:
            html = await self.make_request(session, url)
            if html is not None:
                results = await self.parse_html(session, html)
                logging.info(f"Found {len(results)} results")
                return results

            logging.error("Failed to retrieve HTML content")
            raise RuntimeError("Failed to retrieve HTML content")


async def main(input_json_str: str) -> str:
    """
    Main function to run the GitHub crawler or process specific results.

    Args:
        input_json_str (str): JSON string containing input data or specific results.

    Returns:
        str: JSON string containing crawling results, processed specific results, or error message.
    """
    try:
        input_data = json.loads(input_json_str)

        if isinstance(input_data, dict) and all(key in input_data for key in ['keywords', 'proxies', 'type']):
            # This is input data for the crawler
            crawler = GitHubCrawler(input_data)
            results = await crawler.crawl()
        elif isinstance(input_data, list) and all('url' in item for item in input_data):
            # This is a list of specific results
            results = input_data
        else:
            raise ValueError("Invalid input format")

        return json.dumps(results, indent=2)
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding input JSON: {e}")
        return json.dumps({"error": "Invalid input JSON"})
    except ValueError as e:
        logging.error(f"ValueError: {e}")
        return json.dumps({"error": f"ValueError: {str(e)}"})
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return json.dumps({"error": f"An unexpected error occurred: {str(e)}"})


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        unittest.main(argv=['first-arg-is-ignored'], exit=False)
    else:
        # input_data = {
        #     "keywords": ["python", "django-rest-framework", "jwt"],
        #     "proxies": ["194.126.37.94:8080", "13.78.125.167:8080"],
        #     "type": "Repositories"
        # }

        # Specific results
        input_data = [
            {
                "url": "https://github.com/atuldjadhav/DropBox-Cloud-Storage",
                "extra": {
                    "owner": "atuldjadhav",
                    "language_stats": {
                        "CSS": 52.0,
                        "JavaScript": 47.2,
                        "HTML": 0.8
                    }
                }
            }
        ]

        input_json = json.dumps(input_data)
        result = asyncio.run(main(input_json))
        print("Raw result:")
        print(result)

        try:
            parsed_result = json.loads(result)
            print("\nParsed result:")
            if isinstance(parsed_result, list):
                for item in parsed_result:
                    if isinstance(item, dict) and 'url' in item:
                        print(f"URL: {item['url']}")
                        if 'extra' in item:
                            print(f"Owner: {item['extra']['owner']}")
                            print("Language stats:")
                            for lang, percent in item['extra']['language_stats'].items():
                                print(f"  {lang}: {percent}%")
                    else:
                        print(f"Unexpected item format: {item}")
                    print()
            elif isinstance(parsed_result, dict) and 'error' in parsed_result:
                print(f"Error occurred: {parsed_result['error']}")
            else:
                print(f"Unexpected result format: {parsed_result}")
        except json.JSONDecodeError as e:
            print(f"Error decoding result JSON: {e}")
        except Exception as e:
            print(f"Error processing result: {e}")
