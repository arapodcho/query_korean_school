import os
import re
from datetime import datetime
from typing import List, Optional, Any

import requests
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

url_timetable = "http://open.neis.go.kr/hub/hisTimetable"
URL_SCHOOL_INFO = "http://open.neis.go.kr/hub/schoolInfo"
URL_SCHOOL_SCHEDULE = "http://open.neis.go.kr/hub/SchoolSchedule"

# Read the NEIS service key from environment to avoid hard-coding secrets
# You can set NEIS_SERVICE_KEY or SERVICE_KEY in the environment.
SERVICE_KEY = os.getenv("NEIS_SERVICE_KEY") or os.getenv("SERVICE_KEY") or ""


def _to_yyyymmdd(date_str: str) -> str:
    """Normalize many date formats to YYYYMMDD for NEIS API.

    Supports:
    - YYYYMMDD
    - YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD
    - With time: 'YYYY-MM-DD HH:MM[:SS]' (time is ignored)
    - Korean: 'YYYY년 MM월 DD일' (spaces optional)
    - Fallback: strip non-digits and use first 8 digits if valid
    """
    s = (date_str or "").strip()
    if not s:
        raise ValueError("빈 날짜 문자열입니다.")

    # Fast path: already compact
    if s.isdigit() and len(s) == 8:
        # Validate
        datetime.strptime(s, "%Y%m%d")
        return s

    # Try common explicit formats (date only)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            d = datetime.strptime(s, fmt)
            return d.strftime("%Y%m%d")
        except ValueError:
            pass

    # Try with time component (ignore time)
    for fmt in (
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            d = datetime.strptime(s, fmt)
            return d.strftime("%Y%m%d")
        except ValueError:
            pass

    # Korean pattern: 2025년 11월 6일 (spaces optional)
    m = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", s)
    if m:
        y, mm, dd = m.groups()
        d = datetime(int(y), int(mm), int(dd))
        return d.strftime("%Y%m%d")

    # Fallback: strip non-digits and try first 8 digits
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 8:
        candidate = digits[:8]
        try:
            datetime.strptime(candidate, "%Y%m%d")
            return candidate
        except ValueError:
            pass

    raise ValueError(f"지원하지 않는 날짜 형식입니다: {date_str}")


def _detect_school_level(school_name: str) -> str | None:
    """Infer school level from the Korean school name.

    Returns one of: "초등학교", "중학교", "고등학교" or None if unknown.
    """
    name = (school_name or "").strip()
    if "초등학교" in name:
        return "초등학교"
    if "중학교" in name:
        return "중학교"
    if "고등학교" in name:
        return "고등학교"
    return None

def get_school_info(school_name):
    if not SERVICE_KEY:
        return {
            'valid': False,
            'message': 'Missing NEIS service key. Set NEIS_SERVICE_KEY or SERVICE_KEY in environment.',
            'school_num': 0,
            'school_name': [],
            'school_code': [],
            'org_name': [],
            'org_code': []
        }
    result_value = {
                    'valid': False,
                    'message': 'Initialized',
                    'school_num': 0,                    
                    'school_name': [],
                    'school_code': [],
                    'org_name': [],
                    'org_code': []
                    }
    
    params = {
        'KEY' : SERVICE_KEY,
        'Type': 'json',
        'pIndex': '1',
        'pSize': '100',
        'SCHUL_NM': school_name    
    }
    response = requests.get(URL_SCHOOL_INFO, params=params)
    data = response.json()
    return_code = data.get('RESULT', {}).get('CODE')
    if return_code is None:
        try:
            school_info_list = data.get('schoolInfo', [])[-1].get('row', [])
            for school_info in school_info_list:
                result_value['school_name'].append(school_info.get('SCHUL_NM'))
                result_value['school_code'].append(school_info.get('SD_SCHUL_CODE'))
                result_value['org_name'].append(school_info.get('ATPT_OFCDC_SC_NM'))
                result_value['org_code'].append(school_info.get('ATPT_OFCDC_SC_CODE'))                
            result_value['valid'] = True
            result_value['message'] = "Success to find"
            result_value['school_num'] = len(school_info_list)
        except Exception as e:
            result_value['valid'] = False
            result_value['message'] = f"Error parsing school info: {str(e)}"
            result_value['school_num'] = 0
            result_value['school_name'] = []
            result_value['school_code'] = []
            result_value['org_name'] =  []
            result_value['org_code'] = []
            return result_value                
    else:
        return_message = data.get('RESULT', {}).get('MESSAGE')
        result_value['valid'] = False
        result_value['message'] = return_message
                
    return result_value

def get_school_schedule(school_code, org_code, from_date, to_date):
    if not SERVICE_KEY:
        return {
            'valid': False,
            'message': 'Missing NEIS service key. Set NEIS_SERVICE_KEY or SERVICE_KEY in environment.',
            'schedule_num': 0,
            'event_date': [],
            'event_name': [],
            'event_type': [],
            'event_content': [],
            'valid_grade': [[] for _ in range(6)],
        }
    result_value = {
                    'valid': False,
                    'message': 'Initialized',
                    'schedule_num': 0, 
                    'event_date': [],
                    'event_name': [],
                    'event_type': [],
                    'event_content': [],
                    'valid_grade': [[] for _ in range(6)],                    
                    }    
    params = {
        'KEY' : SERVICE_KEY,
        'Type': 'json',
        'pIndex': '1',
        'pSize': '100',
        'SD_SCHUL_CODE': school_code,
        'ATPT_OFCDC_SC_CODE': org_code,
        'AA_FROM_YMD': from_date,
        'AA_TO_YMD': to_date    
    }
    response = requests.get(URL_SCHOOL_SCHEDULE, params=params)
    data = response.json()
    return_code = data.get('RESULT', {}).get('CODE')
    if return_code is None:
        try:
            schedule_list = data.get('SchoolSchedule', [])[-1].get('row', [])
            for schedule in schedule_list:
                result_value['event_date'].append(schedule.get('AA_YMD'))
                result_value['event_name'].append(schedule.get('EVENT_NM'))
                result_value['event_type'].append(schedule.get('SBTR_DD_SC_NM'))
                result_value['event_content'].append(schedule.get('EVENT_CNTNT'))
                result_value['valid_grade'][0].append(str(schedule.get('ONE_GRADE_EVENT_YN', '')).upper() == 'Y')
                result_value['valid_grade'][1].append(str(schedule.get('TW_GRADE_EVENT_YN', '')).upper() == 'Y')
                result_value['valid_grade'][2].append(str(schedule.get('THREE_GRADE_EVENT_YN', '')).upper() == 'Y')
                result_value['valid_grade'][3].append(str(schedule.get('FR_GRADE_EVENT_YN', '')).upper() == 'Y')
                result_value['valid_grade'][4].append(str(schedule.get('FIV_GRADE_EVENT_YN', '')).upper() == 'Y')
                result_value['valid_grade'][5].append(str(schedule.get('SIX_GRADE_EVENT_YN', '')).upper() == 'Y')            
            result_value['valid'] = True
            result_value['message'] = "Success to find"
            result_value['schedule_num'] = len(schedule_list)
        except Exception as e:
            result_value['valid'] = False
            result_value['message'] = f"Error parsing school schedule: {str(e)}"
            result_value['schedule_num'] = 0            
            return result_value                
    else:
        return_message = data.get('RESULT', {}).get('MESSAGE')
        result_value['valid'] = False
        result_value['message'] = return_message
        result_value['schedule_num'] = 0
                
    return result_value


def get_school_timetable(school_name, from_date, to_date, grade=[1, 2, 3], target_org=None):
    result_value = []
    target_grade = [max(0, min(5, g-1)) for g in grade]
    school_info = get_school_info(school_name)
    if school_info['valid'] and school_info['school_num'] > 0:
        for idx in range(school_info['school_num']):
            # If target_org is None, skip the org_name filter and accept all orgs.
            if target_org is None or school_info['org_name'][idx] == target_org:
                school_code = school_info['school_code'][idx]
                org_code = school_info['org_code'][idx]
                
                schedule_info = get_school_schedule(school_code, org_code, from_date, to_date)
                if schedule_info['valid'] and schedule_info['schedule_num'] > 0:
                    for g in target_grade:
                        for sch_idx in range(schedule_info['schedule_num']):                        
                            if schedule_info['valid_grade'][g][sch_idx]:
                                result_value.append({
                                    'school_name': school_info['school_name'][idx],
                                    'event_date': schedule_info['event_date'][sch_idx],
                                    'event_name': schedule_info['event_name'][sch_idx],
                                    'event_type': schedule_info['event_type'][sch_idx],
                                    'event_content': schedule_info['event_content'][sch_idx],
                                    'grade': g + 1
                                })
                break                

    return result_value


class QueryScheduleSchema(BaseModel):
    """Input schema for QueryKoreanSchoolTool."""

    school_name: str = Field(..., description="학교명 (예: 가평초등학교)")
    from_date: str = Field(
        ...,
        description="시작일. 다양한 형식을 허용(YYYYMMDD, YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD, 'YYYY년 M월 D일', 날짜+시간 등)",
    )
    to_date: str = Field(
        ...,
        description="종료일. 다양한 형식을 허용(YYYYMMDD, YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD, 'YYYY년 M월 D일', 날짜+시간 등)",
    )
    grade: Optional[List[int]] = Field(
        default=None,
        description="선택: 학년 필터(1~6). 미지정 시 학교급 추론에 따라 기본값 적용(초등:1~6, 중/고:1~3)",
    )
    target_org: Optional[str] = Field(
        default=None,
        description="선택: 교육청명 필터(예: 경기도교육청). None이면 필터 없음",
    )


class QueryKoreanSchoolTool(BaseTool):
    """CrewAI custom tool for querying Korean school schedules via NEIS."""

    name: str = "query_schedule_tool"
    description: str = (
        "NEIS API를 통해 특정 학교의 일정(학사일정)을 조회합니다. 입력 날짜는 다양한 형식을 허용하며 내부에서 YYYYMMDD로 정규화합니다."
    )
    args_schema: Any = QueryScheduleSchema

    def _run(
        self,
        school_name: str,
        from_date: str,
        to_date: str,
        grade: Optional[List[int]] = None,
        target_org: Optional[str] = None,
    ) -> Any:
        """Run the tool. Returns list[dict] or an error dict.

        Each schedule item dict includes: school_name, event_date(YYYYMMDD), event_name,
        event_type, event_content, grade.
        """
        # Determine default grades if not provided, based on school level inferred from name
        if grade is None:
            level = _detect_school_level(school_name)
            if level == "초등학교":
                grades = [1, 2, 3, 4, 5, 6]
            else:
                # 중학교/고등학교 또는 알 수 없음 → 1~3학년으로 기본 설정
                grades = [1, 2, 3]
        else:
            grades = grade

        # Normalize dates
        try:
            from_norm = _to_yyyymmdd(from_date)
            to_norm = _to_yyyymmdd(to_date)
        except Exception as e:
            return {"valid": False, "message": f"날짜 형식 오류: {e}", "schedules": []}

        return get_school_timetable(school_name, from_norm, to_norm, grade=grades, target_org=target_org)


# Backward/Convenience export: instantiate the tool so external code can import and use directly
query_schedule_tool = QueryKoreanSchoolTool()

# timetable_info = get_school_timetable("은빛초등학교", '20251001', '20251030', grade=[1,2,3], target_org="경기도교육청")
# print(timetable_info)