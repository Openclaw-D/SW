from __future__ import annotations


class RepositoryError(RuntimeError):
    pass


class RepositoryNotFound(RepositoryError):
    def __init__(self, entity: str, entity_id: str) -> None:
        super().__init__(f"{entity} not found: {entity_id}")
        self.entity = entity
        self.entity_id = entity_id


class RepositoryProjectMismatch(RepositoryError):
    def __init__(self, entity: str, entity_id: str, project_id: str) -> None:
        super().__init__(f"{entity} {entity_id} does not belong to project {project_id}")
        self.entity = entity
        self.entity_id = entity_id
        self.project_id = project_id


class RepositoryConflict(RepositoryError):
    pass
