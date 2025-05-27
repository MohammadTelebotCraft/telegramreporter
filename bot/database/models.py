from sqlalchemy import Column, Integer, String, Boolean, DateTime, UniqueConstraint, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class UserSession(Base):
    __tablename__ = 'user_sessions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    phone_number = Column(String, nullable=False)
    session_string = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint('user_id', 'phone_number', name='_user_phone_uc'),)

    def __repr__(self):
        return f"<UserSession(id={self.id}, user_id={self.user_id}, phone={self.phone_number})>"

class ReportSetting(Base):
    __tablename__ = 'report_settings'

    user_id = Column(Integer, primary_key=True)
    report_message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ReportSetting(user_id={self.user_id}, message_snippet={self.report_message[:30] if self.report_message else ''})>"
