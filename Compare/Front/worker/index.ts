import handler from "vinext/server/app-router-entry";

interface WorkerEnvironment {
  ASSETS: {
    fetch(request: Request): Promise<Response>;
  };
}

interface WorkerExecutionContext {
  waitUntil(promise: Promise<unknown>): void;
  passThroughOnException(): void;
}

const worker = {
  fetch(
    request: Request,
    environment: WorkerEnvironment,
    context: WorkerExecutionContext,
  ): Promise<Response> {
    return handler.fetch(request, environment, context);
  },
};

export default worker;
