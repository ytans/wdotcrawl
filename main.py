from wikidot import Wikidot
import os

SITE = 'http://<hostname>.wikidot.com'
INITIAL_CRAWL = False
STORE = 'store/store.txt'
STORE_DIR = 'store/pages/'
wiki = Wikidot(SITE)

# Create if not exist
if not os.path.exists(STORE):
    f = open(STORE, 'w')
    f.close()

if not os.path.exists(STORE_DIR):
    os.mkdir(STORE_DIR)


def load_store():
    store = {}
    f = open(STORE, 'r')
    for line in [l for l in f.readlines()]:
        s = line.split(',')

        name = s[0]
        if s[1]:
            page_id = int(s[1])
        else:
            page_id = None
        if s[2]:
            revision_id = int(s[2])
        else:
            revision_id = None

        store[name] = (page_id, revision_id)
    return store


def save_store(store):
    f = open(STORE, 'w')
    for (k, v) in store.items():
        l = f'{k},{v[0]},{v[1]}'
        f.write(l + "\n")
    f.close()


def save_latest_revision(page_name, page_id, tags):
    revisions = wiki.get_revisions(page_id, 1)

    first_revision = revisions[0]
    revision_id = first_revision['id']
    # revision_date = first_revision['date']
    # revision_user = first_revision['user']

    revision_source = wiki.get_revision_source(revision_id)

    # Save metadata and source
    f = open(STORE_DIR + page_name + ".txt", "w")
    f.write(str(first_revision) + '\n' + ','.join(tags) + "\n---\n")
    f.write(revision_source)
    f.close()

    return revision_id


# Load store
store = load_store()

if INITIAL_CRAWL:
    # Initial page crawl
    # Get list of edited pages by date ascending
    print("Strategy - Initial")

    START = 1 # Modify if download is stopped and resumption is needed
    for i, pages in enumerate(wiki.list_pages(1000000, START, True)):
        print(f"Page {i + 1} - {len(pages)} items")
        for page_name in pages:
            # Already downloaded (or at least with revision)
            if page_name in store:
                print(f"{page_name} already exists, skipping for now...")
                continue

            print(f"Downloading {page_name}")
            (page_id, tags) = wiki.get_page_id(page_name)
            revision_id = save_latest_revision(page_name, page_id, tags)
            store[page_name] = (page_id, revision_id)

        # Save store after each batch of pages
        save_store(store)
else:
    # List of pages by date descending (latest first)
    # Get list of (changed) pages, until there's a page with known revision
    print("Strategy - Cached")

    # List of lists of pages
    to_retrieve = []
    for i, pages in enumerate(wiki.list_pages(1000000, 1, False)):
        print(f"Page {i + 1} - {len(pages)} items")

        # Add to queue
        to_retrieve.append(pages)

        # Get last page
        last_page_name = pages[-1]
        (last_page_id, _) = wiki.get_page_id(last_page_name)

        # Get revision
        revisions = wiki.get_revisions(last_page_id, 1)
        first_revision = revisions[0]
        revision_id = first_revision['id']

        # Revision matched, don't need to look to older history
        if last_page_name in store:
            if store[last_page_name][1] == int(revision_id):
                break
            else:
                print(f"Page {last_page_name} revision mismatch, looking at next page")
        else:
            print(f"Page {last_page_name} not in store, looking at next page")

    # Retrieve the pages, from oldest to newest
    to_retrieve.reverse()
    for pages in to_retrieve:
        for page_name in pages:
            print(f"Downloading {page_name}")
            (page_id, tags) = wiki.get_page_id(page_name)
            revision_id = save_latest_revision(page_name, page_id, tags)
            store[page_name] = (page_id, revision_id)

        # Save store after each batch of pages
        save_store(store)
