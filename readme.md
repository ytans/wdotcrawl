This is a fork of a fork to make continuous backups of a Wikidot Wiki.

##### Dependencies
* Python 3
* python-beautifulsoup4
* python-requests

##### Examples:
For initial crawl,
change `SITE` and `INITIAL_CRAWL` to `True`.\
Change `START` to resume this process from a particular point.

Once initial crawl is finished, change `INITIAL_CRAWL` to `False` to continuously get updates.\
The program will only grab the relevant updates (for the most part).

To invoke the program:
```
$ python3 main.py
```

Downloading of large sites might take a while. If anything breaks, just restart the same command, it'll continue from where it crashed.
