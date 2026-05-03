import test from 'node:test'; import assert from 'node:assert/strict'; import { defaultBrowserConfig,getServerAppConfig } from '../lib/config';
test('browser config exposes web_app proxy paths',()=>{assert.equal(defaultBrowserConfig.backendProxyBasePath,'/api/backend'); assert.equal(defaultBrowserConfig.authApiBasePath,'/api/auth')});
test('server config has backend base url default',()=>{assert.equal(getServerAppConfig().backendBaseUrl,'http://127.0.0.1:8000')});
