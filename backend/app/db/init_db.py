import logging
from backend.app.db.session import engine, Base, SessionLocal
from backend.app.db.models import User
from backend.app.services.auth import get_password_hash
from backend.app.config import settings

logger = logging.getLogger(__name__)


def init_database():
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified/created successfully.")

    # Seed admin user if not exists
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.username == settings.INITIAL_ADMIN_USERNAME).first()
        if not admin_user:
            admin_user = User(
                username=settings.INITIAL_ADMIN_USERNAME,
                email=settings.INITIAL_ADMIN_EMAIL,
                hashed_password=get_password_hash(settings.INITIAL_ADMIN_PASSWORD),
                role="admin"
            )
            db.add(admin_user)
            db.commit()
            logger.info("Default administrator seeded: %s", settings.INITIAL_ADMIN_USERNAME)
    finally:
        db.close()


if __name__ == "__main__":
    init_database()
