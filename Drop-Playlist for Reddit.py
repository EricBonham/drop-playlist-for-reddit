import praw, re, spotipy
import spotipy.util as util
import sys, os, pprint
from tornado import httpclient
from tornado.concurrent import Future
import asyncio
import json
from time import time
import urllib
import tornado.queues
from tornado import gen
from tornado.ioloop import IOLoop
import configparser

config = configparser.ConfigParser()
config.read_file(open('config.ini'))
reddit = praw.Reddit(client_id = config['Reddit']['client_id'],
                     client_secret = config['Reddit']['client_secret'],
                     username = config['Reddit']['username'],
                     password = config['Reddit']['password'],
                     user_agent = config['Reddit']['user_agent'])

post = reddit.submission(url=config['Reddit']['post_url'])
comments = post.comments
comments.replace_more(int(config['Reddit']['limit']))
Playlist=[]

# regex 2.0 ((?:[A-Z](?:\w|\.)*\s)+(?:\s*-\s*)+(?:[A-Z]\w*\s)*(?:[A-Z](?:\w|\.)*)+)
# regex 1.0 ((?:[A-Z][a-z]*\s)+(?:\s*-\s*)+(?:[A-Z][a-z]*\s)*(?:[A-Z][a-z]*)+)
# best regex ever ((?:[A-Z][\w|\.|$|']*\s)+(?:\s*[-|by]\s*)+(?:[A-Z][\w|$|-|']*\s)*(?:[A-Z][\w|-|'|?]*)+)
 
def SearchSong(text):
    regex = r"((?:[A-Z][\w|\.|$|']*\s)+(?:\s*[-|by]\s*)+(?:[A-Z][\w|$|-|']*\s)*(?:[A-Z][\w|-|'|?]*)+)"
    matches = re.findall(regex, text)
    for song in matches:
        song = song.replace('by','-')
        Playlist.append(song)


for comment in comments:
    text = comment.body.replace('\n', ' ')
    SearchSong(text)

print(len(Playlist))
print(len(list(set(Playlist))))
Playlist=list(set(Playlist))

username = config['Spotify']['user_id']
privacy = config['Spotify']['playlistprivacy']
print(privacy)
scope = 'playlist-modify-{}'.format(privacy)


try:
    token = util.prompt_for_user_token(username, scope)
    print(token)
except:
    os.remove(".cache-{}".format(username))
    token = util.prompt_for_user_token(username)


spotify = spotipy.Spotify(auth = token)
spotify.trace = False


track_uris=[]
LeftSongs=[]

def SpotifyRequest(songname):
    url='https://api.spotify.com/v1/search?q={}&type=track&limit=1'.format(urllib.parse.quote(songname))
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json', 'Authorization': 'Bearer '+token}
    Request = httpclient.HTTPRequest(url, method='GET', headers=headers)
    return Request    

@gen.coroutine
def async_fetch_future():
    while True:
        song = yield q.get()
        try:
            response = yield http_client.fetch(SpotifyRequest(song))
            results = json.loads(response.body.decode('utf-8'))
            for i, t in enumerate(results['tracks']['items']):
                track_uris.append(t['uri'].replace('spotify:track:',''))
        except (httpclient.HTTPError, IOError,ValueError) as e:
            print(e.code)
            LeftSongs.append(song)
            pass
        finally:
            q.task_done()

@gen.coroutine
def put_in_queue():
    for i in range(10):
        IOLoop.current().spawn_callback(async_fetch_future)
    for song in Playlist:
        yield q.put(song)
    yield q.join()
        
q = tornado.queues.Queue(40)
http_client = httpclient.AsyncHTTPClient()
http_client.configure(None, max_clients=10)
IOLoop.current().run_sync(put_in_queue)
    

#get synchronously songs that generated api errors
print(LeftSongs)
print(len(LeftSongs))
for song in LeftSongs:
    results = spotify.search(q=LeftSongs[LeftSongs.index(song)], type='track', limit = 1)
    for i, t in enumerate(results['tracks']['items']):
        track_uris.append(t['uri'].replace('spotify:track:',''))
print(len(track_uris))

if privacy == 'private':
    playlists = spotify.user_playlist_create(username, config['Spotify']['playlistname'], public=False)
elif privacy == 'public':
    playlists = spotify.user_playlist_create(username, config['Spotify']['playlistname'], public=True)

#worst loop ever
start=0
check=0
remaining=0
for i in range(len(track_uris)):
    check=check+1
    if check==100:
        trackadd = spotify.user_playlist_add_tracks(username, playlists['id'], track_uris[start:i])
        start=i
        check=0
        remaining=0
    remaining=remaining+1
trackadd = spotify.user_playlist_add_tracks(username, playlists['id'], track_uris[-remaining:])



