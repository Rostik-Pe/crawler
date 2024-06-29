import random
import asyncio
import aiohttp
import json
import os
from bs4 import BeautifulSoup, Tag
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

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

    def __init__(self, crawler_data: Dict[str, Any]):
        """
        Initialize GitHubCrawler with input data.

        Args:
            crawler_data (Dict[str, Any]): Dictionary containing 'keywords', 'proxies', and 'type'.
        """
        logging.info(f"Initializing GitHubCrawler with input data: {crawler_data}")
        self.keywords: List[str] = crawler_data['keywords']
        self.proxies: List[str] = crawler_data['proxies']
        self.search_type: str = crawler_data['type']
        self.base_url: str = 'https://github.com/search'
        self.delay: Optional[int, float] = 0.5  # delay between requests
        self.timeout: Optional[int, float] = 10

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

    @staticmethod
    def save(data):
        output_dir = 'output_results'
        os.makedirs(output_dir, exist_ok=True)
        file_name = os.path.join(output_dir, f'{datetime.now().strftime("%Y_%m_%d_%H_%M_%S")}_items.json')
        with open(file_name, 'w') as f:
            json.dump(data, f, indent=4)

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
            return await self._perform_request(session, url)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logging.error(f"Error making request: {e}")
            return
        except Exception as e:
            logging.error(f"Unexpected error in make_request: {e}")
            return
        finally:
            await asyncio.sleep(self.delay)

    async def _perform_request(self, session: aiohttp.ClientSession, url: str):
        async with session.get(url, proxy=None, timeout=self.timeout) as response:
            response.raise_for_status()
            content = await response.text()
            if not content.strip():
                logging.warning("Received empty content from server")
                return
            return content

    @staticmethod
    def validate_html(html: str) -> None:
        """
        Validate the HTML content.

        Args:
            html (str): HTML content to validate.

        Raises:
            ValueError: If the HTML content is invalid.
        """
        if not isinstance(html, str):
            logging.error(f"Invalid HTML content type: {type(html)}")
            raise ValueError(f"Invalid HTML content type: {type(html)}. Expected str.")

        if not html.strip():
            logging.warning("Empty HTML content")
            raise ValueError("Empty HTML content")

    @staticmethod
    def create_soup(html: str) -> BeautifulSoup:
        """
        Create a BeautifulSoup object from HTML content.

        Args:
            html (str): HTML content to parse.

        Returns:
            BeautifulSoup: Parsed HTML object.

        Raises:
            ValueError: If there's an error parsing the HTML.
        """
        try:
            return BeautifulSoup(html, 'html.parser', from_encoding='utf-8')
        except Exception as e:
            logging.error(f"Error creating BeautifulSoup object: {e}")
            raise ValueError(f"Error parsing HTML: {e}")

    def extract_language_stats(self, soup: BeautifulSoup) -> Dict[str, str]:
        """
        Extract language statistics from the parsed HTML.

        Args:
            soup (BeautifulSoup): Parsed HTML object.

        Returns:
            Dict[str, str]: Dictionary of language names and their percentages.
        """
        lang_div_tag = self.find_language_div(soup)
        li_elements = lang_div_tag.find_all('li') if lang_div_tag else []

        return {
            language: percentage
            for language, percentage in map(self.extract_language_info, li_elements)
            if language and percentage
        }

    @staticmethod
    def find_language_div(soup: BeautifulSoup) -> Optional[Tag]:
        """Find the div containing language information."""
        border_grid_rows = soup.find_all('div', class_='BorderGrid-row')
        return border_grid_rows[-1] if border_grid_rows else None

    @staticmethod
    def extract_language_info(li: Tag) -> tuple[Optional[str], Optional[str]]:
        """Extract language name and percentage from a list item."""
        language_span = li.find('span', class_='text-bold')
        if not language_span:
            return None, None

        language_name = language_span.text.strip()
        percentage_span = language_span.find_next_sibling('span')
        percentage = percentage_span.text.strip() if percentage_span else None

        return language_name, percentage

    async def parse_html(self, html: str) -> Dict[str, Any]:
        """
        Parse HTML content asynchronously using BeautifulSoup.

        Args:
            html (str): HTML content to parse.

        Returns:
            Dict[str, Any]: Dictionary containing parsed results.

        Raises:
            ValueError: If the HTML content is invalid.
        """
        self.validate_html(html)
        soup = self.create_soup(html)
        language_stats = self.extract_language_stats(soup)

        return {"language_stats": language_stats}

    async def crawl(self) -> None:
        """
        Perform crawling of GitHub search results asynchronously.

        Raises:
            RuntimeError: If failed to retrieve HTML content.
        """
        url = self.create_search_url()
        logging.info(f"Crawling URL: {url}")

        async with aiohttp.ClientSession() as session:
            content = await self.make_request(session, url)
            repositories = self.extract_repositories(content)
            output_data = await self.process_repositories(session, repositories)
            self.save(output_data)

    @staticmethod
    def extract_repositories(content: str) -> List[Dict[str, str]]:
        """Extract repository data from JSON content."""
        repositories_meta_data = json.loads(content)
        repositories = repositories_meta_data['payload']['results']
        return [
            {
                'owner': repo['repo']['repository']['owner_login'],
                'repo_name': repo['repo']['repository']['name'],
            }
            for repo in repositories
        ]

    async def process_repositories(self, session: aiohttp.ClientSession, repositories: List[Dict]) -> List[Dict]:
        """Process each repository to gather additional data."""
        tasks = [self.process_single_repository(session, repo) for repo in repositories]
        return [_result for _result in await asyncio.gather(*tasks) if _result is not None]

    async def process_single_repository(self, session: aiohttp.ClientSession, repo: Dict[str, str]) -> Optional[Dict]:
        """Process a single repository to gather additional data."""
        url = f'https://github.com/{repo['owner']}/{repo['repo_name']}/'
        extra_content_html = await self.make_request(session, url)

        if extra_content_html is None:
            return

        language_stats = await self.parse_html(extra_content_html)
        return {
            'url': url,
            'extra': {
                'owner': repo['owner'],
                'language_stats': language_stats['language_stats']
            },
        }


async def main(input_json_str: str) -> str:
    """
    Main function to run the GitHub crawler or process specific results.

    Args:
        input_json_str (str): JSON string containing input data or specific results.

    Returns:
        str: JSON string containing crawling results, processed specific results, or error message.
    """
    try:
        data = json.loads(input_json_str)

        if isinstance(data, dict) and all(key in data for key in ['keywords', 'proxies', 'type']):
            crawler = GitHubCrawler(data)
            results = await crawler.crawl()
        elif isinstance(data, list) and all('url' in item for item in data):
            results = data
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


def generate_input_data_json(inp_data_key: str, inp_data_type: str) -> str:
    """
        Generate JSON string from input data.

        Args:
            inp_data_key (str): Input data key to split into keywords.
            inp_data_type (str): Input data type.

        Returns:
            str: JSON string representing input data.
        """
    input_data = {
        'keywords': inp_data_key.split(),
        "proxies": ["194.126.37.94:8080", "13.78.125.167:8080"],
        'type': inp_data_type,
    }
    return json.dumps(input_data)


if __name__ == "__main__":

    input_keywords = input('Enter keywords separated by spaces: ')
    input_type = input('Enter search type. Example: Repositories, Issues: ')

    input_json = generate_input_data_json(input_keywords, input_type)
    result = asyncio.run(main(input_json))
