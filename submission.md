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

- **How I reproduced it:** On Sunday, I set the seeded user's streak to 12 and their last listen to Saturday. I posted a listen to an existing song at `POST /songs/<song_id>/listen`. The streak logic reset the streak instead of increasing it to 13. The existing Sunday regression test also reproduced this: it failed with a streak of 1 instead of 2.
- **How I found the root cause:** I traced the listen request from `routes/songs.py` to `record_listening_event()` and then `update_listening_streak()` in `services/streak_service.py`. I read the Sunday test in `tests/test_streaks.py` and ran it before changing the code; it failed at the expected streak assertion. This pointed to the streak update condition rather than event creation or the route.
- **The root cause:** `update_listening_streak()` only incremented when one day had passed and the current weekday was not Sunday. Python's `weekday()` returns `6` for Sunday, so a valid Saturday-to-Sunday consecutive listen missed the increment branch and fell through to the reset branch.
- **My fix:** I removed the Sunday restriction. The streak now increments whenever exactly one calendar day has passed, regardless of the weekday. Same-day listens still do not add to the streak, and a gap of more than one day still resets it.
- **My side-effect check:** I ran `tests/test_streaks.py`. Its cases check a new user's streak, consecutive-day listening, multiple listens on the same day, a skipped day, and the Saturday-to-Sunday boundary. All pass after the change.
- **AI use:** I used AI to help explain the weekday condition and review the test result. I verified the cause against the route, service, and test code before changing the condition.

## Issue #2 — How I reproduced it

- **Setup:** The seed data makes Nova and Darius friends. I set Darius's latest listening event to 20 hours ago and moved his older events back two days.
- **Check:** I opened `GET /feed/<nova_id>/listening-now`. Darius appeared in the results with his listen from the previous day, showing that yesterday's activity was still included.

## Issue #3 — How I reproduced it

- **Setup:** I used the seeded song “Crown Heights Anthem,” which has multiple tags.
- **Search:** I opened `GET /songs/search?q=Anthem`.
- **Result:** “Crown Heights Anthem” appeared more than once in the `results` list.

## Issue #4 — How I reproduced it

- **Setup:** I used Darius as the rater and a song shared by Nova.
- **Rate:** I sent `POST /songs/<song_id>/rate` with `{"user_id":"<darius_id>","score":5}`. The app returned a saved rating with a score of 5.
- **Check:** I opened `GET /users/<nova_id>/notifications`. It returned the existing playlist-add notification, but no notification about Darius rating Nova's song.

## Issue #5 — How I reproduced it

- **Setup:** I opened the seeded “Friday Energy” playlist, which contains seven songs.
- **Check:** I requested `GET /playlists/<playlist_id>/songs`. The response had `count: 6` and listed six songs, so the playlist's last song was missing.