# Mixtape Codebase Map

## Application structure

- `app.py` creates the Flask app, configures SQLAlchemy from environment variables, registers the four route blueprints, and creates the database tables inside the application context.
- `models.py` defines seven SQLAlchemy models: `User`, `Tag`, `Song`, `ListeningEvent`, `Rating`, `Playlist`, and `Notification`. It also defines the `friendships` and `song_tags` many-to-many association tables and the `playlist_entries` association table, which stores playlist position and who added each song. Model `to_dict()` methods provide JSON-ready representations.
- `routes/` contains the HTTP layer. `songs.py` exposes song search/detail, rating, and listening endpoints; `playlists.py` exposes playlist creation, detail, song listing, and song addition; `users.py` exposes user profiles, streaks, and notifications; `feed.py` exposes friends-listening-now and activity feeds. The route handlers parse request data, call service functions, and format JSON responses.
- `services/` contains feature logic. `search_service.py` handles song lookup; `playlist_service.py` creates playlists and retrieves their metadata and ordered songs; `streak_service.py` records listening events and manages streak data; `notification_service.py` handles ratings, playlist additions, and notification retrieval/read state; and `feed_service.py` builds friends' listening-now and activity feeds.
- `seed_data.py` recreates the database and populates example users, friendships, tags, songs, listening events, playlists, and a notification.
- `tests/` contains pytest coverage for streak behavior, song search, and playlist retrieval. Each test module creates an app configured with an in-memory SQLite database.


## Data flow: rating a song

1. A client sends `POST /songs/<song_id>/rate` with `user_id` and `score` in a JSON body. The endpoint is registered by the songs blueprint in `app.py`.
2. The handler in `routes/songs.py` reads those fields and passes them, along with the URL's `song_id`, to `rate_song()` in `services/notification_service.py`.
3. `rate_song()` checks that the score is within the allowed range and that the song and user exist. It looks for an existing rating for that user and song, then updates it or creates a `Rating` record.
4. The service commits the database transaction and returns the rating. The route serializes it with `to_dict()` and responds with JSON.

## Organization patterns

- Flask blueprints group endpoints by feature and are mounted under `/songs`, `/playlists`, `/users`, and `/feed`.
- Routes generally handle HTTP concerns, while service functions own reusable feature operations and interact with the database through the shared `db` instance.
- Models define relationships and serialization, while association tables represent friendships, song tags, and ordered playlist membership.
- Services use model instances and dictionaries as their inputs and outputs; routes consistently present results as JSON.
- Tests use isolated in-memory databases so their data is independent of the local seeded database.

**Issue #1 — My listening streak keeps resetting**

- **How I reproduced it:** On Sunday, I set the seeded user's streak to 12 and their last listen to Saturday, then sent a listen request to `POST /songs/<song_id>/listen`. The streak reset to 1 instead of increasing to 13. Before changing the code, `tests/test_streaks.py` also failed its Saturday-to-Sunday check: it got 1 instead of the expected 2.
- **How I found the root cause:** I followed the request from `routes/songs.py` to `record_listening_event()` and `update_listening_streak()` in `services/streak_service.py`. Then I ran the Sunday test in `tests/test_streaks.py` before making a change. The listen event was being recorded; the failure occurred when the streak update handled the Sunday date.
- **The root cause:** The increment condition required both that one day had passed and that the current day was not Sunday. Python reports Sunday as `6` from `weekday()`, so a listen on Sunday skipped the increment and reached the reset branch.
- **My fix:** I removed the weekday restriction. Now, if the last listen was exactly one calendar day earlier, the streak increments on any day. Same-day listens still leave the streak unchanged, and missing more than one day still resets it.
- **My side-effect check:** I ran `.\.venv\Scripts\python.exe -m pytest tests\test_streaks.py -q`. All five tests passed, covering a new streak, consecutive days, multiple listens on one day, a skipped day, and listening Saturday then Sunday with a streak of 12 becoming 13.

## AI usage

- For Issue #1, I asked AI to explain the Sunday weekday condition and help interpret the failing test. I checked the route, service, and test myself, confirmed the pre-fix failure, and used that evidence to guide the change.
- For Issue #2, I used AI to reason about the difference between a rolling 24-hour window and the current calendar day. I verified the existing cutoff in the service and tested events on both sides of midnight.
- For Issue #3, I used AI to explain how a SQL join affects result rows. I confirmed the query joined to the song-tags table and ran the multi-tag search test before making the change.
- For Issue #4, I used AI to compare the rating and playlist-add call paths. I verified the missing notification step in the service and added tests for notifying a song's sharer and avoiding self-notifications.
- For Issue #5, I used AI to help interpret the list slice in `get_playlist_songs()`. I verified the returned query results against the failing count and order tests before removing the slice.

**Issue #2 — Friends Listening Now shows people from yesterday**

- **How I reproduced it:** Using the seeded friendship between Nova and Darius, I set Darius's latest listen to 20 hours ago and moved his older listens back two days. I requested `GET /feed/<nova_id>/listening-now`. Darius still appeared with yesterday's listen.
- **How I found the root cause:** I traced the feed endpoint in `routes/feed.py` to `get_friends_listening_now()` in `services/feed_service.py`. I compared the function's time cutoff with the issue's morning-after example: the query used the current time minus 24 hours, which includes late-evening listens from yesterday.
- **The root cause:** The feed used a rolling 24-hour window rather than checking whether a listen happened on the current calendar day. A listen from 11 p.m. yesterday can therefore remain in the feed the next morning.
- **My fix:** I changed the query window to start at midnight UTC today and end at the current time. This includes today's events and excludes yesterday's and future-dated events. The change is limited to `get_friends_listening_now()`; the activity feed is unchanged.
- **My side-effect check:** I tested with one friend event from yesterday and another from today. Listening Now returned only today's event, while `get_activity_feed()` still returned both. I also ran `.\.venv\Scripts\python.exe -m pytest tests\test_streaks.py -q`; all five streak tests passed.

**Issue #3 — The same song keeps showing up twice in search**

- **How I reproduced it:** I searched for the seeded multi-tag song with `GET /songs/search?q=Anthem`. “Crown Heights Anthem” appeared three times in the results.
- **How I found the root cause:** I traced the search endpoint in `routes/songs.py` to `search_songs()` in `services/search_service.py`. The search query filters on song title and artist, then joins each matching song to its rows in the song-tags table. The multi-tag test in `tests/test_search.py` confirmed that this produced three result rows for the song.
- **The root cause:** The query joined songs to their tags even though search did not filter on tags. A song with three tag rows therefore appeared three times in the query results.
- **My fix:** I removed the unnecessary join and its unused imports. The song's `to_dict()` method still provides its tags, so the response retains the tag list while each matching song is selected once.
- **My side-effect check:** I ran `.\.venv\Scripts\python.exe -m pytest tests\test_search.py -q`. All five tests passed, covering matching searches, songs with zero, one, and multiple tags, and no-match searches. I also restarted the app and repeated the browser search; “Crown Heights Anthem” appeared once and still included its tags.

**Issue #4 — I got notified when a friend added my song to a playlist but not when they rated it**

- **How I reproduced it:** I used Darius as the rater and a song shared by Nova. I posted a score of 5 to `POST /songs/<song_id>/rate`, then checked `GET /users/<nova_id>/notifications`. The rating was saved, but Nova had no rating notification.
- **How I found the root cause:** I traced the rating endpoint in `routes/songs.py` to `rate_song()` in `services/notification_service.py`. I compared it with `add_to_playlist()` in that same service, which creates a notification after a friend adds a song. `rate_song()` saved or updated the rating and committed it, then returned without creating a notification.
- **The root cause:** The rating flow had no step to notify the song's sharer after a different user submitted a rating.
- **My fix:** After saving the rating, `rate_song()` now uses the existing `create_notification()` helper to notify the song's sharer. It skips the notification when users rate their own songs.
- **My side-effect check:** The two new notification tests pass, confirming that rating another user's song creates a notification with the rater, song, and score, while rating one's own song does not create a self-notification. The streak and search tests also pass (10 total).

**Issue #5 — The last song in a playlist never shows up**

- **How I reproduced it:** I opened the seeded “Friday Energy” playlist, which contains seven songs, using `GET /playlists/<playlist_id>/songs`. The response reported six songs and omitted the final one. The focused playlist tests also failed before the fix: a five-song playlist returned four songs, and its final title was missing from the ordered list.
- **How I found the root cause:** I traced the playlist endpoint in `routes/playlists.py` to `get_playlist_songs()` in `services/playlist_service.py`. The database query returned songs ordered by position. The returned list was shortened afterward, which matched the missing-last-song symptom.
- **The root cause:** The function serialized `songs[:-1]`, a Python slice that excludes the final item. This removed the last song regardless of playlist size.
- **My fix:** I changed the return expression to serialize all queried songs. The query ordering and empty-playlist behavior remain unchanged.
- **My side-effect check:** I ran `.\.venv\Scripts\python.exe -m pytest tests\test_playlists.py -q`. All three tests passed, covering all songs returned, correct ordering, and an empty playlist. I also ran the full suite with `.\.venv\Scripts\python.exe -m pytest tests -q`; all 15 tests passed.