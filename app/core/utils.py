import re
from fastapi import Request

async def parse_form_data(request: Request) -> dict:
    """
    Преобразует плоскую структуру FormData (application/x-www-form-urlencoded)
    в вложенный словарь, пригодный для Pydantic.
    
    Пример:
    questions[0][text] -> {'questions': [{'text': '...'}]}
    questions[0][options][1] -> {'questions': [{'options': {1: '...'} }]} 
    (позже options преобразуются в список)
    """
    form_data = await request.form()
    result = {
        "title": form_data.get("title"),
        "description": form_data.get("description"),
        "tag_names": form_data.getlist("tag_names"),
        "questions": {}  # Временно храним как dict по индексам
    }

    # Регулярки для парсинга ключей
    # questions[0][text]
    q_pattern = re.compile(r"questions\[(\d+)\]\[(\w+)\]")
    # questions[0][options][0]
    opt_pattern = re.compile(r"questions\[(\d+)\]\[options\]\[(\d+)\]")

    for key, value in form_data.items():
        # 1. Проверяем опции (они более вложенные, проверяем первыми)
        opt_match = opt_pattern.match(key)
        if opt_match:
            q_idx, o_idx = map(int, opt_match.groups())
            if value.strip(): # Игнорируем пустые опции
                result["questions"].setdefault(q_idx, {}).setdefault("options", {})[o_idx] = value
            continue

        # 2. Проверяем поля вопроса
        q_match = q_pattern.match(key)
        if q_match:
            q_idx, field = q_match.groups()
            q_idx = int(q_idx)
            
            if q_idx not in result["questions"]:
                result["questions"][q_idx] = {"options": {}} # Init
            
            # Обработка чекбокса (HTML не шлет false, шлет "on" или ничего)
            if field == "is_required":
                result["questions"][q_idx][field] = True
            else:
                result["questions"][q_idx][field] = value

    # Финализация: Превращаем dict вопросов в list и сортируем
    # Также превращаем dict опций в list
    final_questions = []
    for q_idx in sorted(result["questions"].keys()):
        q_data = result["questions"][q_idx]
        
        # Если чекбокс не пришел, значит False (у HTML форм такая логика)
        if "is_required" not in q_data:
            q_data["is_required"] = False
            
        # Превращаем опции {0: "A", 2: "B"} в список ["A", "B"]
        # Сортируем по ключам (индексам из HTML), чтобы порядок сохранился
        options_dict = q_data.get("options", {})
        q_data["options"] = [options_dict[i] for i in sorted(options_dict.keys())]
        
        # Если позиция не пришла (вдруг), ставим индекс цикла
        if "position" not in q_data:
            q_data["position"] = q_idx

        final_questions.append(q_data)

    result["questions"] = final_questions
    return result