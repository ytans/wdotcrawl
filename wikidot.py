import requests
import random
from bs4 import BeautifulSoup
import time
from urllib.parse import urlparse, urljoin
import pathlib
import os
import shutil
import imghdr
from timeit import default_timer as timer

# Implements various queries to Wikidot engine through its AJAX facilities


class Wikidot:
    def __init__(self, site):
        self.site = site        # Wikidot site to query

        # strip out trailing /, if it exists
        if self.site[-1] == '/':
            self.site = self.site[:-1]
        self.sitename = urlparse(site).hostname.lower()
        self.delay = 1000        # Delay between requests in msec
        self.debug = False      # Print debug messages
        self.next_timeslot = time.process_time()   # Can call immediately
        self.max_retries = 5
        self.failed_images = set()

    # Downloads file if it doesn't exist
    def maybe_download_file(self, url, file_path):
        if url in self.failed_images:
            if self.debug:
                print(" ! ", url, "already failed, skipping")
            return False

        if os.path.exists(file_path):
            if self.debug:
                print(" - ", file_path, "exists, skipping")
            return False

        #self._wait_request_slot()

        try:
            dirpath = os.path.dirname(file_path)
            os.makedirs(dirpath, exist_ok=True)
        except OSError as e:
            if e.errno == 36:
                print("Path too long", e)
                return False
            else:
                raise  # re-raise previously caught exception

        if self.debug:
            print(" < downloading", url, "to" ,file_path, "dirpath", dirpath)

        # In case of e. g. 500 errors
        retries = 0
        while retries < self.max_retries:
            self._wait_request_slot()

            headers = requests.utils.default_headers()
            # Pretty generic user-agent, but we append a unique none for us
            # Makes wikimedia happy
            headers.update({ "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:32.0) Gecko/20100101 Firefox/32.0 wdotcrawler/1.0"})
            start = timer()

            try:
                req = requests.get(url, stream=True, timeout=30)
            except requests.exceptions.RequestException:
                print('request exception')

                retries += 1
                time.sleep(retries * retries * retries) # up to ~2 minutes
                continue
            # except urllib3.exceptions.ReadTimeoutError:
            #     print('read timeout')

            #     retries += 1
            #     time.sleep(retries * retries * retries) # up to ~2 minutes
            #     continue

            if req.status_code >= 500:
                print(' ! 500 error for ' + url + ', retries ' + str(retries) + '/' + str(self.max_retries))
                # In case of debug enabled, we already printed this above
                if not self.debug:
                    print(' - ', req)

                retries += 1
                time.sleep(retries * retries * retries)
                continue

            if req.status_code >= 400:
                self.failed_images.add(url)
                return False

            try:
                # In case of 404 errors or other stuff that indicates
                # some bug in how we handle or request things
                req.raise_for_status()

                req.raw.decode_content = True
                with open(file_path, 'wb') as out_file:
                    shutil.copyfileobj(req.raw, out_file)

                if imghdr.what(file_path) is None:
                    print('Downloaded invalid image', url)
                    os.remove(file_path)
                    self.failed_images.add(url)
                    return False


                if self.debug:
                    print(" - downloaded file size", os.path.getsize(file_path), "in", round(timer() - start, 2))

                return True
            except OSError as e:
                if e.errno == 36:
                    print("Filename to long", e)
                    return False
                else:
                    raise  # re-raise previously caught exception
            except Exception as e:
                print(' ! Failed to download', e, req, url)
                raise e

        print('Failed too many times for', url)
        return False

    # To honor usage rules, we wait for self.delay between requests.
    # Low-level query functions call this before every request to Wikidot./
    def _wait_request_slot(self):
        tm = time.process_time()
        if self.next_timeslot - tm > 0:
            time.sleep(self.next_timeslot - tm)
        self.next_timeslot = tm + self.delay / 1000

        pass

    # Makes a Wikidot AJAX query. Returns the response+title or throws an error.
    def queryex(self, params, urlAppend = None):
        token = "".join(random.choice('abcdefghijklmnopqrstuvwxyz0123456789') for i in range(8))
        cookies = {"wikidot_token7": token}
        params['wikidot_token7'] = token

        if self.debug:
            print(' - ', params)
            print(' - ', cookies)

        url = self.site+'/ajax-module-connector.php'
        if urlAppend is not None:
            url += urlAppend

        # In case of e. g. 500 errors
        retries = 0
        while retries < self.max_retries:
            if retries > 0:
                print(" ! retry", retries, "of", self.max_retries)

            self._wait_request_slot()

            start = timer()
            try:
                req = requests.request('POST', url, data=params, cookies=cookies, timeout=30)
            except requests.exceptions.RequestException:
                print('request timed out!')
                retries += 1
                time.sleep(retries * retries * retries)
                continue

            if self.debug:
                print(' * ajax request completed in', round(timer() - start, 2))

            # Usually a 502 error, recovers immediately
            if req.status_code >= 500:
                retries += 1
                print(' ! 500 error for ' + url + ', retries ' + str(retries) + '/' + str(self.max_retries))

                # In case of debug enabled, we already printed this above
                if not self.debug:
                    print(req, params)

                # Be nice, double wait delay for errors
                self._wait_request_slot()

                # Extra nice, sleep longer (expoential increase), hope for the
                # server to recover
                time.sleep(retries * retries * retries)

                continue

            try:
                # In case of 404 errors or other stuff that indicates
                # some bug in how we handle or request things
                req.raise_for_status()
            except Exception as e:
                print(' ! Failed to get response from wikidot', e, req, url, params)

            try:
                json = req.json()
            except Exception as e:
                print(' ! Failed to get response from wikidot', e, req, url, params)
                if retries < self.max_retries:
                    retries += 1
                    #self._wait_request_slot()
                    time.sleep(retries * retries * retries)
                    continue

                raise e

            if json['status'] == 'ok':
                return json['body'], (json['title'] if 'title' in json else '')
            else:
                print(" ! error in response", json)

                retries += 1
                time.sleep(retries * retries * retries)
                continue

        print(' ! Failed too many times', url, params, cookies)
        raise Exception('Failed too many times for ' + url)

    # Same but only returns the body, most responses don't have titles
    def query(self, params, urlAppend = None):
        return self.queryex(params, urlAppend)[0]

    # List all pages for the site.

    # Raw version
    # For the supported formats (module_body) see:
    # See https://github.com/gabrys/wikidot/blob/master/php/modules/list/ListPagesModule.php
    def list_pages_raw(self, limit, offset, asc=False):
        res = self.query({
          'moduleName': 'list/ListPagesModule',
          'limit': limit if limit else '10000',
          'perPage': '50',
          'module_body': '%%page_unix_name%%',
          'separate': 'false',
          'p': str(offset),
          'order': 'dateEditedAsc' if asc else 'dateEditedDesc',
        }, '/p/' + str(offset))
        return res

    # Client version
    def list_pages(self, limit, offset=1, asc=False):
        while True:
            pages = []
            raw = self.list_pages_raw(limit, offset, asc).replace('<br/>',"\n")
            soup = BeautifulSoup(raw, 'html.parser')

            for entry in soup.div.p.text.split('\n'):
                pages.append(entry)

            if self.debug:
                print(' - Pages found:', len(pages))

            yield pages

            targets = soup.find_all('span','target')
            if len(targets) < 2:
                print(" ! Unable to find next listing page, not enough target spans")
                break

            next_url = targets[-1].a.get('href').split('/')
            if len(next_url) > 0 and next_url[-1].isnumeric():
                next_page = int(next_url[-1])

                if self.debug:
                    print(' - Next listing page', next_page)

            else:
                print(" ! invalid next url", next_url)
                break

            #next_page = int(targets[0].a.text)

            current_spans = soup.find_all('span','current')
            if len(current_spans) > 0:
                current_page = int(current_spans[0].text)

                if self.debug:
                    print(' - Current listing page', current_page)

            else:
                print(" ! unable to find current page")
                break

            if next_page != offset + 1:
                if self.debug:
                    print(' ! Next page is wrong', next_page, 'hopefully at the end')
                break

            offset += 1

            print(" - Fetching listing page", offset)

        return pages


    # Retrieves internal page_id by page unix_name.
    # Page IDs are required for most of page functions.

    def get_page_id(self, page_unix_name):
        # The only freaking way to get page ID is to load the page! Wikidot!
        self._wait_request_slot()
        url = self.site+'/'+page_unix_name + '/noredirect/true';

        if self.debug:
            print(" > fetching", url)

        start = timer()
        retries = 0
        req = None
        while retries < self.max_retries:
            try:
                req = requests.request('GET', url, timeout=30)
            except requests.exceptions.RequestException:
                print('request timed out!')
                retries += 1
                time.sleep(retries * retries * retries)
                continue

            if req.status_code >= 500:
                print(' ! 500 error for ' + url + ', retries ' + str(retries) + '/' + str(self.max_retries))
                retries += 1
                time.sleep(retries * retries * retries)
                continue

            req.raise_for_status()
            break

        if self.debug:
            print(' * page id request completed in', round(timer() - start, 2))

        soup = BeautifulSoup(req.text, 'html.parser')

        # Tags of page
        tags = []
        page_tags_tag = soup.select('.page-tags span a')
        for item in page_tags_tag:
            for child in item.children:
                tags.append(child)

        page_id = None
        for item in soup.head.find_all('script'):
            text = item.string
            if text is None:
                #print("No text in script item", item)
                continue

            pos = text.find("WIKIREQUEST.info.pageId = ")
            if pos >= 0:
                pos += len("WIKIREQUEST.info.pageId = ")
                crlf = text.find(";", pos)
                if crlf >= 0:
                    page_id = int(text[pos:crlf])
                else:
                    page_id = int(text[pos:])

        if page_id:
            return (page_id, tags)

        raise Exception('Failed to get page_id for ' + page_unix_name)


    # Retrieves a list of revisions for a page.
    # See https://github.com/gabrys/wikidot/blob/master/php/modules/history/PageRevisionListModule.php

    # Raw version
    def get_revisions_raw(self, page_id, limit):
        res = self.query({
          'moduleName': 'history/PageRevisionListModule',
          'page_id': page_id,
          'page': '1',
          'perpage': limit if limit else '10000',
          'options': '{"all":true}'
        })

        soup = BeautifulSoup(res, 'html.parser')
        return soup.table.contents

    # Client version
    def get_revisions(self, page_id, limit):
        revs = []
        raw = self.get_revisions_raw(page_id, limit)
        for tr in raw:
            if tr.name != 'tr': continue # there's a header + various junk

            # RevID is stored as a value of an INPUT field
            rev_id = tr.input['value'] if tr.input else None
            if rev_id is None: continue # can't parse
            attachment_action = tr.find("span", attrs={"title": "file/attachment action"})
            attached_file = False
            if attachment_action is not None:
                attached_file = True
                print(" - was attchment", rev_id)

            # Unixtime is stored as a CSS class time_*
            rev_date = 0
            date_span = tr.find("span", attrs={"class": "odate"})
            if date_span is not None:
                for cls in date_span['class']:
                    if cls.startswith('time_'):
                        rev_date = int(cls[5:])
            else:
                print(" ! no odate found")

            # Username in a last <a> under <span class="printuser">
            user_span = tr.find("span", attrs={"class": "printuser"})
            last_a = None
            for last_a in user_span.find_all('a'): pass
            rev_user = last_a.getText() if last_a else None


            # Comment is in the last TD of the row
            last_td = None
            for last_td in tr.find_all('td'): pass
            rev_comment = last_td.getText() if last_td else ""

            revs.append({
                'id': rev_id,
                'date': rev_date,
                'user': rev_user,
                'comment': rev_comment,
                'attached_file': attached_file,
            })
        return revs

    # topics in forum: http://www.scp-wiki.net/forum/c-###/sort/start
    # -> div class 'title'
    #   -> a href= http://www.scp-wiki.net/forum/t-####/foobar (foobar not important)

    # posts in topic http://www.scp-wiki.net/forum/t-####/
    # -> div id 'thread-container'
    #   -> div class 'post-container'
    #       -> div class = 'post', id = 'post-####'
    #           -> div class 'title'
    #           -> div class 'content'
    #   -> div class 'post-container'
    #       -> ...
    #       -> div class 'post-container'
    #           -> ...

    #def get_forum_post_revisions(self, post_id):
    #    res = self.query({
    #      'moduleName': 'forum/sub/ForumPostRevisionsModule',
    #      'postId': post_id,
    #    })
    #    revisions = []
    #    soup = BeautifulSoup(res, 'html.parser')
    #    for row in soup.find_all("tr"):
    #        columns = row.find_all("td")

    #        if len(columns) != 3:
    #            raise Exception('Invalid row in post history for ' + str(post_id))

    #        user = columns[0].find('a').getText()
    #        time = columns[1].find('span').getText()
    #        rev_id_js = columns[0].find('a')['href']
    #        match = re.search(r'showRevision\(event, ([0-9]+)\)', rev_id_js)
    #        rev_id = match.group(1)

    #        revisions.append({
    #            'id': rev_id,
    #            'user': user,
    #            'time': time,
    #            })

    # Retrieves revision source for a revision.
    # There's no raw version because there's nothing else in raw.
    def get_revision_source(self, rev_id):
        res = self.query({
          'moduleName': 'history/PageSourceModule',
          'revision_id': rev_id,
          # We don't need page id
        })
        # The source is HTMLified but BeautifulSoup's getText() will decode that
        # - htmlentities
        # - <br/>s in place of linebreaks
        # - random real linebreaks (have to be ignored)
        soup = BeautifulSoup(res, 'html.parser')
        return soup.div.getText().lstrip(' \r\n')

    # Retrieves the rendered version + additional info unavailable in get_revision_source:
    # * Title
    # * Unixname at the time
    #
    # TODO: I think this could fetch the source as well, so we don't need to
    # fetch two pages (the fetch source function above).
    def get_revision_version_raw(self, rev_id):
        res = self.queryex({
          'moduleName': 'history/PageVersionModule',
          'revision_id': rev_id,
        })
        return res

    def get_revision_version(self, rev_id):
        res = self.get_revision_version_raw(rev_id) # this has title!
        soup = BeautifulSoup(res[0], 'html.parser')

        # Extract list of images

        # TODO: to get the right revision that added them, we need to go back
        # and amend the commits that are flagged as attached_file above,
        # because we can't get the image file name or URL reliably until they
        # are added to the page source, wikidot itself doesn't store this information.
        # So much hassle for little value, we get the empty commits when images
        # are added anyways.
        images = []
        for img_div in soup.find_all("div", attrs={"class": "scp-image-block"}):
            img_src = None
            img_name = ""
            full_link = img_div.find("a")
            if full_link is not None:
                # Check if it has a thumbnail, otherwise we can't trust that it is the original
                img = full_link.find("img", attrs={"class": "enlarge"})
                if img is not None:
                    img_src = full_link["href"]
                    img_name = img["alt"]

            if img_src is None:
                img = img_div.find("img")
                if img is not None:
                    img_src = img["src"]
                    img_name = img["alt"]

            if img_src is None:
                continue

            # Just in case, I don't think it ever happens, but resolve '..'
            # juuuust in case someone tries to be funny
            img_url = urlparse(urljoin(img_src, "."))
            url_path = pathlib.Path(img_url.path)

            img_path = ""
            if img_url.netloc != "":
                img_path = img_url.netloc + "/"
                if img_url.netloc[-1] != '/':
                    img_path += '/'

            if img_url.path != "" and img_url.path[0] == '/':
                img_path += img_url.path[1:]
            else:
                img_path += img_url.path

            if img_path == "" or img_path[-1] == "/":
                img_path += img_name

            images.append({"src": img_src, "filename": img_name, "filepath": "images/" + img_path})



        # First table is a flyout with revision details. Remove and study it.
        unixname = None
        details = soup.find("div", attrs={"id": "page-version-info"}).extract()
        for tr in details.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) < 2: continue
            if tds[0].getText().strip() == 'Page name:':
                unixname = tds[1].getText().strip()

        if unixname is None:
            raise Exception('Failed to find unixname for ' + rev_id)

        return {
          'rev_id': rev_id,
          'unixname': unixname,
          'title': res[1],
          'content': str(soup), # only content remains
          'images': images,
        }
