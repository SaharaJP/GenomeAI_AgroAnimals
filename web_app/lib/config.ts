export type BrowserAppConfig = {
  appName: string;
  backendProxyBasePath: string;
  authApiBasePath: string;
  authCookieNames: {
    accessToken: string;
    refreshToken: string;
  };
};

export type ServerAppConfig = BrowserAppConfig & {
  backendBaseUrl: string;
};

export const defaultBrowserConfig: BrowserAppConfig = {
  appName: 'GenomeAI AgroAnimals Web',
  backendProxyBasePath: '/api/backend',
  authApiBasePath: '/api/auth',
  authCookieNames: {
    accessToken: 'ga_access_token',
    refreshToken: 'ga_refresh_token',
  },
};

export function getBrowserAppConfig(): BrowserAppConfig {
  return defaultBrowserConfig;
}

export function getServerAppConfig(): ServerAppConfig {
  return {
    ...defaultBrowserConfig,
    backendBaseUrl:
      process.env.GENOMEAI_API_BASE_URL ||
      process.env.GENOMEAI_WEB_BACKEND_URL ||
      'http://127.0.0.1:8000',
  };
}
