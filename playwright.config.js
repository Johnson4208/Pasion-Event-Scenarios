import {defineConfig} from '@playwright/test';
export default defineConfig({
 testDir:'./tests',fullyParallel:false,workers:1,reporter:'list',
 use:{baseURL:'http://127.0.0.1:5173',channel:process.env.PLAYWRIGHT_CHANNEL||undefined,
  launchOptions:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH}:{},
  viewport:{width:1440,height:1000},trace:'retain-on-failure'},
 webServer:{command:'npm run dev:frontend',url:'http://127.0.0.1:5173',reuseExistingServer:true},
});
