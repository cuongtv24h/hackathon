import { expect, test } from '@playwright/test'

declare const process: { env: Record<string, string | undefined> }

const liveOnly = process.env.E2E_LIVE !== '1'

test.describe('MVP live capability flows', () => {
  test.skip(liveOnly, 'Set E2E_LIVE=1 and use a dedicated E2E Supabase environment.')

  test('RAG answer renders at least one citation', async ({ page }) => {
    await page.goto('/')
    await page.getByLabel('Nội dung').fill('Bảng giá dịch vụ kỹ thuật là bao nhiêu?')
    await page.getByRole('button', { name: 'Gửi' }).click()
    await expect(page.getByLabel('Information assistance response')).toBeVisible()
    await expect(page.getByLabel('Citations').locator('li').first()).toBeVisible()
  })

  test('emergency request renders the safety banner', async ({ page }) => {
    await page.goto('/')
    await page.getByLabel('Tác vụ').selectOption('emergency_safety')
    await page.getByLabel('Nội dung').fill('Tôi đau ngực dữ dội và khó thở')
    await page.getByRole('button', { name: 'Gửi' }).click()
    await expect(page.getByLabel('Emergency safety banner')).toBeVisible()
  })

  test('booking uses dependent dropdowns, creates pending appointment and status lookup', async ({ page }) => {
    let confirmationRequest: { payload: Record<string, unknown>; idempotencyKey: string } | undefined
    page.on('request', (request) => {
      if (request.url().includes('appointment-booking:execute') && request.headers()['idempotency-key']) {
        confirmationRequest = {
          payload: request.postDataJSON() as Record<string, unknown>,
          idempotencyKey: request.headers()['idempotency-key'],
        }
      }
    })

    await page.goto('/')
    await page.getByLabel('Tác vụ').selectOption('appointment_booking')
    const specialty = page.getByLabel('Chuyên khoa')
    await expect(specialty.locator('option').nth(1)).toBeAttached()
    await specialty.selectOption({ index: 1 })
    const doctor = page.getByLabel('Bác sĩ')
    await expect(doctor.locator('option').nth(1)).toBeAttached()
    await doctor.selectOption({ index: 1 })
    const slot = page.getByLabel('Khung giờ')
    await expect(slot.locator('option').nth(1)).toBeAttached()
    await slot.selectOption({ index: 1 })
    await page.getByLabel('Họ tên').fill('E2E Demo Patient')
    await page.getByLabel('Số điện thoại').fill('0900000099')
    await page.getByLabel('Ngày sinh').fill('1990-01-01')
    await page.getByLabel('Lý do khám').fill('E2E booking validation')
    await page.getByRole('button', { name: 'Kiểm tra và xác nhận' }).click()
    await page.getByRole('button', { name: 'Xác nhận đặt lịch' }).click()
    await expect(page.getByLabel('Pending appointment')).toBeVisible()
    const appointmentId = await page.getByLabel('Appointment summary').locator('dd').first().textContent()
    expect(appointmentId).toMatch(/^HEN-\d{4}-\d{4}$/)
    expect(confirmationRequest?.idempotencyKey).toBeTruthy()

    await page.getByLabel('Tác vụ').selectOption('appointment_status')
    await page.getByLabel('Mã lịch hẹn').fill(appointmentId ?? '')
    await page.getByRole('button', { name: 'Gửi' }).click()
    await expect(page.getByLabel('Appointment status')).toContainText('pending')
  })

  test('admin resolves the configured live content conflict', async ({ page }) => {
    const conflictId = process.env.E2E_CONFLICT_ID
    test.skip(!conflictId, 'Set E2E_CONFLICT_ID from a dedicated E2E database fixture.')
    await page.goto('http://127.0.0.1:5174')
    await expect(page.getByLabel('Content management dashboard')).toBeVisible()
    await page.locator('li', { hasText: conflictId }).getByRole('button', { name: 'Resolve conflict' }).click()
    await page.getByLabel(/Ghi chú xử lý/).fill('Resolved by live E2E validation')
    await page.getByRole('button', { name: 'Lưu resolution audit' }).click()
    await expect(page.getByText('resolved')).toBeVisible()
  })
})
