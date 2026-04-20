declare module 'react' {
  export type ReactNode = any;
  export type PropsWithChildren<P = {}> = P & { children?: ReactNode };
  export type ButtonHTMLAttributes<T = any> = any;
  export type FormEvent<T = any> = any;
  export function createContext<T>(value: T): any;
  export function useContext<T>(context: any): T;
  export function useEffect(effect: () => void | (() => void), deps?: any[]): void;
  export function useMemo<T>(factory: () => T, deps: any[]): T;
  export function useState<T>(value: T): [T, (next: T) => void];
}

declare namespace React {
  type ReactNode = any;
  type FormEvent<T = any> = any;
}

declare namespace JSX {
  interface IntrinsicElements {
    [elemName: string]: any;
  }
}

declare module 'react/jsx-runtime' {
  export const Fragment: any;
  export function jsx(type: any, props: any, key?: any): any;
  export function jsxs(type: any, props: any, key?: any): any;
}

declare module 'next' {
  export interface NextConfig {
    [key: string]: any;
  }
}

declare module 'next/navigation' {
  export function redirect(href: string): never;
  export function useRouter(): { replace: (href: string) => void; refresh: () => void };
  export function usePathname(): string;
}

declare module 'next/link' {
  const Link: any;
  export default Link;
}

declare module 'next/headers' {
  export function cookies(): Promise<{
    has: (name: string) => boolean;
    get: (name: string) => { value?: string } | undefined;
  }>;
}

declare module 'next/server' {
  export class NextRequest extends Request {
    nextUrl: { search?: string };
  }
  export class NextResponse extends Response {
    static json(body?: any, init?: any): NextResponse;
    cookies: {
      set: (name: string, value: string, options?: any) => void;
    };
  }
}

declare const process: { env: Record<string, string | undefined> };

declare module 'node:test' { const test: any; export default test; }
declare module 'node:assert/strict' { const assert: any; export default assert; }
