import pytest

from app import create_app, db
from models import Notification, Song, User
from services.notification_service import rate_song


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


def test_rating_song_notifies_its_sharer(app):
    with app.app_context():
        sharer = User(username="sharer", email="sharer@example.com")
        rater = User(username="rater", email="rater@example.com")
        db.session.add_all([sharer, rater])
        db.session.flush()
        song = Song(title="Test Song", artist="Test Artist", shared_by=sharer.id)
        db.session.add(song)
        db.session.commit()

        rating = rate_song(rater.id, song.id, 5)

        notification = Notification.query.filter_by(user_id=sharer.id).one()
        assert rating.score == 5
        assert notification.notification_type == "song_rated"
        assert "rater" in notification.body
        assert "Test Song" in notification.body
        assert "5 out of 5" in notification.body


def test_rating_own_song_does_not_notify_rater(app):
    with app.app_context():
        user = User(username="owner", email="owner@example.com")
        db.session.add(user)
        db.session.flush()
        song = Song(title="Test Song", artist="Test Artist", shared_by=user.id)
        db.session.add(song)
        db.session.commit()

        rate_song(user.id, song.id, 4)

        assert Notification.query.count() == 0
