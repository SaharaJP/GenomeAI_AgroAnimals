declare module 'react' {
  export type ReactNode = any;
  export type PropsWithChildren<P = {}> = P & { children?: ReactNode };
  export type ButtonHTMLAttributes<T = any> = any;
  export type FormEvent<T = any> = any;
  export type MouseEvent<T = any> = any;
  export type ChangeEvent<T = any> = any;
  export type KeyboardEvent<T = any> = any;
  export type CSSProperties = any;
  export type Ref<T> = { current: T | null };
  export type RefObject<T> = { readonly current: T | null };
  export type MutableRefObject<T> = { current: T };

  export interface Context<T> {
    readonly _ctx?: T;
    Provider: (props: { value: T; children?: ReactNode }) => any;
  }

  export function createContext<T>(defaultValue: T | null): Context<T>;
  export function useContext<T>(context: Context<T>): T;

  export function useEffect(effect: () => void | (() => void), deps?: any[]): void;
  export function useLayoutEffect(effect: () => void | (() => void), deps?: any[]): void;

  export function useState<S>(initialState: () => S): [S, (action: S | ((prevState: S) => S)) => void];
  export function useState<S>(initialState: S): [S, (action: S | ((prevState: S) => S)) => void];
  export function useState<S = undefined>(): [S | undefined, (action: S | undefined | ((prevState: S | undefined) => S | undefined)) => void];

  export function useReducer<S, A>(reducer: (state: S, action: A) => S, initialState: S): [S, (action: A) => void];

  export function useMemo<T>(factory: () => T, deps: any[]): T;

  export function useCallback<T extends (...args: any[]) => any>(callback: T, deps: any[]): T;

  export function useRef<T>(initialValue: T): { current: T };
  export function useRef<T>(initialValue: T | null): { current: T | null };
  export function useRef<T = undefined>(): { current: T | undefined };

  export function useId(): string;

  export function use<T>(value: PromiseLike<T> | Context<T>): T;
}

declare namespace React {
  type ReactNode = any;
  type FormEvent<T = any> = any;
  type CSSProperties = any;
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
  export function useRouter(): { replace: (href: string) => void; refresh: () => void; push: (href: string) => void; back: () => void };
  export function usePathname(): string;
  export function useSearchParams(): {
    get(key: string): string | null;
    has(key: string): boolean;
    getAll(key: string): string[];
    entries(): IterableIterator<[string, string]>;
    keys(): IterableIterator<string>;
    values(): IterableIterator<string>;
    toString(): string;
  };
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
    nextUrl: { search?: string; searchParams: URLSearchParams };
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
