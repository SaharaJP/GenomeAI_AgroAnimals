import { getBrowserAppConfig } from '@/lib/config';
// backend proxy base path: /api/backend
const config=getBrowserAppConfig();
async function parseError(response:Response){try{const body=await response.json();if(body&&typeof body==='object'&&'detail' in body)return String((body as {detail?:unknown}).detail)}catch{}return response.statusText||`HTTP ${response.status}`}
export async function apiFetch<T>(path:string,init?:RequestInit):Promise<T>{const response=await fetch(`${config.backendProxyBasePath}${path.startsWith('/')?path:`/${path}`}`,{...init,headers:{'content-type':'application/json',...(init?.headers||{})},credentials:'include',cache:'no-store'});if(!response.ok)throw new Error(await parseError(response));return response.json() as Promise<T>}
export async function authFetch<T>(path:string,init?:RequestInit):Promise<T>{const response=await fetch(`${config.authApiBasePath}${path.startsWith('/')?path:`/${path}`}`,{...init,headers:{'content-type':'application/json',...(init?.headers||{})},credentials:'include',cache:'no-store'});if(!response.ok)throw new Error(await parseError(response));return response.json() as Promise<T>}
