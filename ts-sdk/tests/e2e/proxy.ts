import {
  createServer,
  request as httpRequest,
  type IncomingMessage,
  type ServerResponse,
} from 'node:http';

interface Route {
  prefix: string;
  target: string;
  stripPrefix: boolean;
}

export interface ProxyHandle {
  close: () => void;
}

interface ProxyOptions {
  listenPort: number;
  routes: Route[];
}

export async function createProxy({ listenPort, routes }: ProxyOptions): Promise<ProxyHandle> {
  const server = createServer((req: IncomingMessage, res: ServerResponse) => {
    const url = req.url ?? '/';
    const route = routes.find((r) => url.startsWith(r.prefix));
    if (!route) {
      res.statusCode = 404;
      res.end();
      return;
    }

    const forwardedPath = route.stripPrefix ? url.slice(route.prefix.length - 1) : url;
    const target = new URL(forwardedPath, route.target);

    const upstream = httpRequest(
      {
        hostname: target.hostname,
        port: target.port || 80,
        path: target.pathname + target.search,
        method: req.method,
        headers: {
          ...(req.headers as Record<string, string | string[] | undefined>),
          host: `${target.hostname}:${target.port}`,
        },
      },
      (upstreamRes) => {
        res.writeHead(upstreamRes.statusCode ?? 502, upstreamRes.headers);
        upstreamRes.pipe(res);
      },
    );
    upstream.on('error', (err) => {
      res.statusCode = 502;
      res.end(`proxy error: ${err.message}`);
    });
    req.pipe(upstream);
  });

  await new Promise<void>((resolve) => server.listen(listenPort, '127.0.0.1', resolve));
  return { close: () => server.close() };
}
