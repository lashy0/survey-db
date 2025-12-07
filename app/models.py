import enum
from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Interval,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SurveyStatus(str, enum.Enum):
    """Enumeration for survey lifecycle statuses."""
    draft = "draft"
    active = "active"
    completed = "completed"
    archived = "archived"


class QuestionType(str, enum.Enum):
    """Enumeration for types of questions supported."""
    single_choice = "single_choice"
    multiple_choice = "multiple_choice"
    text_answer = "text_answer"
    rating = "rating"


class UserRole(str, enum.Enum):
    """Enumeration for user permission roles."""
    user = "user"
    creator = "creator"
    admin = "admin"


# Many-to-Many relationship table between Surveys and Tags
survey_tags = Table(
    "survey_tags",
    Base.metadata,
    Column("survey_id", Integer, ForeignKey("surveys.survey_id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.tag_id", ondelete="CASCADE"), primary_key=True),
)


class Country(Base):
    """
    Represents a country for user location normalization.

    Attributes:
        country_id (int): Primary key.
        name (str): Unique name of the country.
    """
    __tablename__ = "countries"

    country_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # Relationships
    users: Mapped[List["User"]] = relationship(back_populates="country")


class User(Base):
    """
    Represents a registered user on the platform.

    Attributes:
        user_id (int): Primary key.
        first_name (str): User's first name.
        last_name (str): User's last name (optional).
        email (str): Unique email address.
        password_hash (str): Hashed password.
        birth_date (date): Date of birth (must be in the past).
        city (str): City name (optional).
        country_id (int): Foreign key to countries table.
        role (UserRole): Role (user, creator, admin).
        registration_date (datetime): Timestamp of registration.
    """
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("birth_date < CURRENT_DATE", name="check_birth_date"),
    )

    user_id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    country_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("countries.country_id", ondelete="SET NULL")
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"), default=UserRole.user, nullable=False
    )
    registration_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    country: Mapped[Optional["Country"]] = relationship(back_populates="users")
    created_surveys: Mapped[List["Survey"]] = relationship(back_populates="author")
    responses: Mapped[List["SurveyResponse"]] = relationship(back_populates="user")


class Tag(Base):
    """
    Represents a tag/category for surveys.

    Attributes:
        tag_id (int): Primary key.
        name (str): Unique tag name.
    """
    __tablename__ = "tags"

    tag_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # Relationships
    surveys: Mapped[List["Survey"]] = relationship(
        secondary=survey_tags, back_populates="tags"
    )


class Survey(Base):
    """
    Represents a survey created by a user.

    Attributes:
        survey_id (int): Primary key.
        title (str): Survey title.
        description (str): Survey description.
        status (SurveyStatus): Current state of the survey.
        author_id (int): ID of the creator.
        created_at (datetime): Creation timestamp.
        start_date (datetime): When the survey becomes active.
        end_date (datetime): When the survey closes.
    """
    __tablename__ = "surveys"
    __table_args__ = (
        CheckConstraint("end_date > start_date", name="check_dates"),
    )

    survey_id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[SurveyStatus] = mapped_column(
        Enum(SurveyStatus, name="survey_status"), default=SurveyStatus.draft, nullable=False
    )
    author_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    author: Mapped[Optional["User"]] = relationship(back_populates="created_surveys")
    tags: Mapped[List["Tag"]] = relationship(
        secondary=survey_tags, back_populates="surveys"
    )
    questions: Mapped[List["Question"]] = relationship(
        back_populates="survey", cascade="all, delete-orphan"
    )
    responses: Mapped[List["SurveyResponse"]] = relationship(
        back_populates="survey", cascade="all, delete-orphan"
    )


class Question(Base):
    """
    Represents a single question within a survey.

    Attributes:
        question_id (int): Primary key.
        survey_id (int): ID of the parent survey.
        question_text (str): The actual question.
        question_type (QuestionType): Type (choice, text, rating).
        position (int): Ordering position in the survey.
        is_required (bool): Whether an answer is mandatory.
    """
    __tablename__ = "questions"

    question_id: Mapped[int] = mapped_column(primary_key=True)
    survey_id: Mapped[int] = mapped_column(
        ForeignKey("surveys.survey_id", ondelete="CASCADE")
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, name="question_type_enum"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    survey: Mapped["Survey"] = relationship(back_populates="questions")
    options: Mapped[List["Option"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )
    answers: Mapped[List["UserAnswer"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class Option(Base):
    """
    Represents a choice option for single/multiple choice questions.

    Attributes:
        option_id (int): Primary key.
        question_id (int): ID of the parent question.
        option_text (str): The text of the option.
        is_correct (bool): Used for quizzes/tests (optional).
    """
    __tablename__ = "options"

    option_id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.question_id", ondelete="CASCADE")
    )
    option_text: Mapped[str] = mapped_column(String(255), nullable=False)
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)

    # Relationships
    question: Mapped["Question"] = relationship(back_populates="options")


class SurveyResponse(Base):
    """
    Represents a user's session of taking a survey.

    Attributes:
        response_id (int): Primary key.
        survey_id (int): The survey being taken.
        user_id (int): The user taking the survey (can be NULL if anonymous, but logic here assumes registered).
        started_at (datetime): When the user started.
        completed_at (datetime): When the user finished.
        duration (timedelta): Automatically computed duration.
        ip_address (str): User's IP.
        device_type (str): Mobile/Desktop etc.
    """
    __tablename__ = "survey_responses"
    # Ensure unique attempt per user per survey
    __table_args__ = (
        CheckConstraint("completed_at >= started_at", name="check_completion_time"),
    )

    response_id: Mapped[int] = mapped_column(primary_key=True)
    survey_id: Mapped[int] = mapped_column(
        ForeignKey("surveys.survey_id", ondelete="CASCADE")
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Generated column (requires PostgreSQL 12+)
    duration: Mapped[Optional[timedelta]] = mapped_column(
        Interval, 
        Computed("completed_at - started_at", persisted=True)
    )
    
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    device_type: Mapped[Optional[str]] = mapped_column(String(50))

    # Relationships
    survey: Mapped["Survey"] = relationship(back_populates="responses")
    user: Mapped[Optional["User"]] = relationship(back_populates="responses")
    answers: Mapped[List["UserAnswer"]] = relationship(
        back_populates="response", cascade="all, delete-orphan"
    )


class UserAnswer(Base):
    """
    Represents a specific answer to a specific question in a response.

    Attributes:
        answer_id (int): Primary key.
        response_id (int): The parent session.
        question_id (int): The question being answered.
        selected_option_id (int): For choice questions.
        text_answer (str): For text questions.
    """
    __tablename__ = "user_answers"
    __table_args__ = (
        CheckConstraint(
            "selected_option_id IS NOT NULL OR text_answer IS NOT NULL", 
            name="check_answer_content"
        ),
    )

    answer_id: Mapped[int] = mapped_column(primary_key=True)
    response_id: Mapped[int] = mapped_column(
        ForeignKey("survey_responses.response_id", ondelete="CASCADE")
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.question_id", ondelete="CASCADE")
    )
    selected_option_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("options.option_id")
    )
    text_answer: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    response: Mapped["SurveyResponse"] = relationship(back_populates="answers")
    question: Mapped["Question"] = relationship(back_populates="answers")
    selected_option: Mapped[Optional["Option"]] = relationship("Option")
