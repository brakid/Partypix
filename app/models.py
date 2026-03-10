import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from app.database import Base


class Photo(Base):
    __tablename__ = "photos"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    upload_timestamp = Column(DateTime, default=datetime.now)
    storage_path = Column(String, nullable=False)
    thumbnail_path = Column(String, nullable=True)
    
    tags = relationship("Tag", secondary="photo_tags", back_populates="photos")


class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    label = Column(String, unique=True, nullable=False)
    
    photos = relationship("Photo", secondary="photo_tags", back_populates="tags")


photo_tags = Table(
    "photo_tags",
    Base.metadata,
    Column("photo_id", String, ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", String, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
)
