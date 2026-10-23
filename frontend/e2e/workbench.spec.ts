import { test, expect } from '@playwright/test'

// Real OIDC login only; no bypass route or injected browser token is shipped.
test.beforeEach(async ({ page }) => {
  test.skip(!process.env.E2E_USERNAME || !process.env.E2E_PASSWORD, '需要管理员测试账号')
  await page.goto('/dev')
  await page.locator('input[name="username"]').fill(process.env.E2E_USERNAME!)
  await page.locator('input[name="password"]').fill(process.env.E2E_PASSWORD!)
  await page.locator('button[name="login"], input[name="login"]').click()
  await expect(page.getByRole('button', { name: '退出登录', exact: true })).toBeVisible()
})

test('editor survives navigation and real worker reports success and failure', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const editable = page.getByRole('textbox', { name: '起草笔记编辑器' })
  await editable.fill('来自浏览器的风电项目验证笔记')
  await page.getByRole('link', { name: /服务连接/ }).click()
  await expect(page.getByRole('heading', { name: '服务连接' })).toBeVisible()
  await page.getByRole('link', { name: /开发工作台/ }).click()
  await expect(editable).toContainText('来自浏览器的风电项目验证笔记')
  await page.getByTestId('run-task').click()
  await expect(page.getByTestId('task-status')).toHaveText('已完成', { timeout: 30_000 })
  await expect(page.getByText('示例结果已保存')).toBeVisible()
  await page.getByLabel('模拟任务失败', { exact: false }).check()
  await page.getByTestId('run-task').click()
  await expect(page.getByTestId('task-status')).toHaveText('执行失败', { timeout: 30_000 })
  await expect(page.getByRole('alert')).toContainText('主动触发的演示失败')
  expect(errors).toEqual([])
})

test('reconnect replays remaining events even when the status query is already terminal', async ({ page }) => {
  let intercepted = false
  let reconnected = false
  await page.route('**/api/v1/tasks/*/events', async (route) => {
    if (!intercepted) {
      intercepted = true
      const response = await route.fetch()
      const firstEvent = (await response.text()).split('\n\n')[0]
      // End the first connection after one event; the worker has already finished.
      await route.fulfill({ status: 200, contentType: 'text/event-stream; charset=utf-8', body: `${firstEvent}\n\n` })
      return
    }
    reconnected = true
    await route.continue()
  })
  await page.getByTestId('run-task').click()
  await expect(page.getByText('示例流程完成', { exact: true })).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('.event-list li')).toHaveCount(6)
  await expect(page.getByTestId('task-status')).toHaveText('已完成')
  expect(reconnected).toBe(true)
})
