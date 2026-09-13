from pydantic import BaseModel


class Technician(BaseModel):
    technician_id: str
    name_alias: str
    skills: list[str]
    certifications: list[str]
    shift_start: str
    shift_end: str
    status: str
    current_zone: str
    max_workload_min: int
