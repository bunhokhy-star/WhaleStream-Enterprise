from typing import List

from controller.service import Service, ServiceHealth


class ServiceRegistry:
    def __init__(self) -> None:
        self._services = {}

    def register(self, service: Service) -> None:
        if service.name in self._services:
            raise ValueError(f"Service already registered: {service.name}")
        self._services[service.name] = service

    def get(self, name: str) -> Service:
        if name not in self._services:
            raise KeyError(f"Service not registered: {name}")
        return self._services[name]

    def all(self) -> List[Service]:
        return list(self._services.values())

    def names(self) -> List[str]:
        return list(self._services.keys())

    def initialize_all(self, context) -> None:
        for service in self.all():
            service.initialize(context)

    def start_all(self) -> None:
        for service in self.all():
            service.start()

    def update_all(self) -> None:
        for service in self.all():
            service.update()

    def stop_all_reverse(self) -> None:
        for service in reversed(self.all()):
            service.stop()

    def health_all(self) -> List[ServiceHealth]:
        return [service.health() for service in self.all()]
