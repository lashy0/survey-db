from pydantic import BaseModel, Field, field_validator, EmailStr, model_validator
from typing import List, Optional, Literal
from datetime import date

class OptionCreate(BaseModel):
    text: str

class QuestionCreate(BaseModel):
    text: str
    type: Literal["single_choice", "multiple_choice", "text_answer", "rating"]
    position: int = 0
    is_required: bool = False
    rating_scale: Optional[int] = None 
    options: List[str] = Field(default_factory=list)

class SurveyCreateForm(BaseModel):
    title: str
    description: str
    tag_names: List[str] = Field(default_factory=list)
    questions: List[QuestionCreate] = Field(default_factory=list)

    @field_validator('questions')
    def sort_questions(cls, v):
        return sorted(v, key=lambda q: q.position)
    
    @model_validator(mode='after')
    def check_logic(self):
        if not self.questions:
            raise ValueError("Опрос должен содержать хотя бы один вопрос")
        
        for q in self.questions:
            # Проверка: есть ли опции у вопросов с выбором
            if q.type in ['single_choice', 'multiple_choice'] and len(q.options) < 2:
                raise ValueError(f"Вопрос '{q.text}' типа '{q.type}' должен иметь минимум 2 варианта ответа")
            
            # Проверка: рейтинг
            if q.type == 'rating':
                if not q.rating_scale or not (2 <= q.rating_scale <= 10):
                    # Если вдруг пришло что-то странное, ставим дефолт или ругаемся
                    # В данном случае просто убедимся, что логика соблюдена
                    pass 
        return self

# Для регистрации
class UserRegister(BaseModel):
    email: EmailStr  # Автоматически проверит формат email
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, description="Минимум 6 символов")

# Для обновления профиля
class UserProfileUpdate(BaseModel):
    full_name: str = Field(..., min_length=2)
    city: Optional[str] = None
    country_id: Optional[int] = None
    birth_date: Optional[date] = None # Pydantic сам преобразует строку "2000-01-01" в date объект

    @field_validator('birth_date', mode='before')
    def parse_empty_date(cls, v):
        # HTML форма шлет пустую строку "", если дата не выбрана. 
        # Pydantic упадет, поэтому превращаем "" в None
        if v == "": return None
        return v

class PasswordChangeForm(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)
    confirm_password: str

    @model_validator(mode='after')
    def check_passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError('Новые пароли не совпадают')
        return self

