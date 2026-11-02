from InspectionOS.skills.contracts import Skill, validate


class SkillRegistry:
    def __init__(self): self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill):
        if skill.spec.skill_id in self._skills: raise ValueError('duplicate skill')
        self._skills[skill.spec.skill_id] = skill

    def get(self, skill_id: str) -> Skill:
        if skill_id not in self._skills: raise ValueError('unregistered skill: '+skill_id)
        return self._skills[skill_id]

    def list(self): return [s.spec for s in self._skills.values()]

    def validate_input(self, skill_id, payload): validate(payload, self.get(skill_id).spec.input_schema)
    def validate_output(self, skill_id, result): validate(result, self.get(skill_id).spec.output_schema)
