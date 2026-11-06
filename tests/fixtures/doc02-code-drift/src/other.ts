export async function run(job: Job) {
  const lock = await acquire(job.id)
  try {
    await job.exec()
  } catch (err) {
    log(err)
  } finally {
    // the guard: never release a lock we do not hold
    if (lock.held) {
      await lock.release()
    }
  }
}

export function helper(x: number) {
  const doubled = x * 2
  return doubled + 1
}
