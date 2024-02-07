import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# ---- things to keep in mind ----
# only crawl these domains
#   *.ics.uci.edu/*
#   *.cs.uci.edu/*
#   *.informatics.uci.edu/*
#   *.stat.uci.edu/*
# traps
#   -infinitely deep directories
#       -calculate deepness of link within directories and set limit
#   -dynamic pages producing an unbounded number of documents
#       -keep track of number of items downloaded within a website directory and set limit
#   -pages with a lot of character to crash memory
# needed info from pages
#   -all hyperlinks
#   -number of words
#   -most common words and their frequencies, ignoring stop words
#       -50 most common words in entire set of pages
# things needed for report
#   -# of unique pages
#   -longest page in # of words
#   -50 most common words
#   -number of subdomains in ics.uci.edu
# redirected links
#   -https://mcs.ics.uci.edu/?p=587 leads to https://mcs.ics.uci.edu/about/curriculum/
#   -for the purposes of the assignment these should be considered unique pages
#   -only discard fragment part in url
# relative URLs
#   -<a href='/filewithinpage'/>
#   -^should be able to detect these and tranform them into the proper absolute URL

url_pattern = '^(https?:\/\/(([a-zA-Z0-9]{2,}\.)*ics\.uci\.edu|([a-zA-Z0-9]{2,}\.)*cs\.uci\.edu|([a-zA-Z0-9]{2,}\.)*informatics\.uci\.edu|([a-zA-Z0-9]{2,}\.)*stat\.uci\.edu)\/[a-zA-Z0-9()@:%_\+.~?&//=]*)(#[a-zA-Z0-9()@:%_\+.~?&//=]*)?$'

def scraper(url, resp):
    links = extract_next_links(url, resp)
    return [link for link in links if is_valid(link)]

def extract_next_links(url, resp):
    # Implementation required.
    # url: the URL that was used to get the page
    # resp.url: the actual url of the page
    # resp.status: the status code returned by the server. 200 is OK, you got the page. Other numbers mean that there was some kind of problem.
    # resp.error: when status is not 200, you can check the error here, if needed.
    # resp.raw_response: this is where the page actually is. More specifically, the raw_response has two parts:
    #         resp.raw_response.url: the url, again
    #         resp.raw_response.content: the content of the page!
    # Return a list with the hyperlinks (as strings) scrapped from resp.raw_response.content

    # ---- IMPLEMENTATION ----
    # look through each word of the content and match it against a regular expression to check if its a url
    # if it is a url, add it to the list

    # use BeautifulSoup to parse HTML information from website, using .get_text() to extract text and .find_all(True) and element['href'] to get hyperlinks
    # pip install beautifulsoup4
    all_links = []
    if resp.status == 200:
        soup = BeautifulSoup(resp.raw_response.text, features='lxml')
        for a in soup.find_all(href=re.compile(url_pattern)):
            href = a.get('href', '/')

            # remove fragment from URL
            url_match = re.match(url_pattern, href)
            all_links.append(url_match.group(0))
    else:
        print("Error")
        print(f'Status code: {resp.status}')
        print(resp.error)
    return all_links

def is_valid(url):
    # Decide whether to crawl this url or not. 
    # If you decide to crawl it, return True; otherwise return False.
    # There are already some conditions that return False.
    try:
        parsed = urlparse(url)
        if parsed.scheme not in set(["http", "https"]):
            return False
        return not re.match(
            r".*\.(css|js|bmp|gif|jpe?g|ico"
            + r"|png|tiff?|mid|mp2|mp3|mp4"
            + r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
            + r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
            + r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
            + r"|epub|dll|cnf|tgz|sha1|bib"
            + r"|thmx|mso|arff|rtf|jar|csv"
            + r"|rm|smil|wmv|swf|wma|zip|rar|gz)$", parsed.path.lower())

    except TypeError:
        print ("TypeError for ", parsed)
        raise
