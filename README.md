# GitHub Crawler

GitHub Crawler is an asynchronous Python script for searching and gathering information from GitHub. It can search for repositories, issues, and wiki pages based on given keywords.

## Features

- Asynchronous crawling for improved performance
- Proxy support to bypass request limitations
- Ability to search for repositories, issues, and wiki pages
- Collection of additional repository information (owner, language statistics)
- Error handling and logging

## Requirements

This script requires Python 3.7 or higher. All necessary dependencies are listed in the `requirements.txt` file.

## Installation

1. Clone the repository:
  git clone https://github.com/yourusername/github-crawler.git
  cd github-crawler
2. Create a virtual environment and activate it:
  python -m venv venv
  source venv/bin/activate  # On Windows use venv\Scripts\activate
3. Install the dependencies:
   pip install -r requirements.txt

## Usage

1. Prepare input data in JSON format. Example:
```json
[
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
```
2. Run the script:
   python github_crawler.py
3. Results will be output in JSON format

## Testing
1. To run unit tests, execute:
  python github_crawler.py test

## License
This project is distributed under the MIT License. See the LICENSE file for more information.

This README provides basic information about the project, installation and usage instructions, and a list of key features. You can customize it further to fit your specific needs or add more details if necessary.
