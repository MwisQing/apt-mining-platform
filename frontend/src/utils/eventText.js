export function formatChineseDate(date = new Date()) {
  const year = date.getFullYear()
  const month = date.getMonth() + 1
  const day = date.getDate()
  return `${year}年${month}月${day}日`
}

export function defaultEventName(date = new Date()) {
  return `银狐-${formatChineseDate(date)}`
}

export function formatIoc(target, port) {
  const cleanTarget = String(target || '').trim()
  const cleanPort = String(port || '').trim()
  if (!cleanTarget) return ''
  return cleanPort ? `${cleanTarget}:${cleanPort}` : cleanTarget
}

export function uniqueDevices(devices) {
  const seen = new Set()
  const result = []
  for (const device of devices || []) {
    const clean = String(device || '').trim().toUpperCase()
    if (!clean || seen.has(clean)) continue
    seen.add(clean)
    result.push(clean)
  }
  return result
}

export function buildEventNote({ ioc, devices, eventName }) {
  const deviceLines = uniqueDevices(devices).join('\n')
  return [
    `线索ioc：${ioc || ''}`,
    '',
    '设备id：',
    deviceLines,
    '',
    eventName || '',
    '',
    '---------------------------------------',
  ].join('\n')
}

export function parseDevicesFromEventNote(text) {
  const lines = String(text || '').split(/\r?\n/)
  const start = lines.findIndex((line) => line.trim().toLowerCase() === '设备id：' || line.trim().toLowerCase() === '设备id:')
  if (start === -1) return []

  const devices = []
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index].trim()
    if (!line) {
      if (devices.length > 0) break
      continue
    }
    if (line.startsWith('线索ioc') || line.startsWith('银狐-') || line.startsWith('---')) break
    devices.push(line)
  }
  return uniqueDevices(devices)
}

export function parseIocFromEventNote(text) {
  const lines = String(text || '').split(/\r?\n/)
  const line = lines.find((item) => item.trim().startsWith('线索ioc：') || item.trim().startsWith('线索ioc:'))
  if (!line) return { target: '', port: '' }

  const raw = line.replace(/^线索ioc[:：]/, '').trim()
  if (!raw) return { target: '', port: '' }

  const ipv6Bracket = raw.match(/^\[([^\]]+)]:(.+)$/)
  if (ipv6Bracket) {
    return { target: ipv6Bracket[1].trim(), port: ipv6Bracket[2].trim() }
  }

  const lastColon = raw.lastIndexOf(':')
  if (lastColon > -1 && raw.indexOf(':') === lastColon) {
    return {
      target: raw.slice(0, lastColon).trim(),
      port: raw.slice(lastColon + 1).trim(),
    }
  }

  return { target: raw, port: '' }
}

function findEventNameLineIndex(lines) {
  const start = lines.findIndex((line) => line.trim().toLowerCase() === '设备id：' || line.trim().toLowerCase() === '设备id:')
  if (start === -1) return -1

  let index = start + 1
  while (index < lines.length) {
    const line = lines[index].trim()
    if (!line) {
      index += 1
      break
    }
    if (line.startsWith('线索ioc') || line.startsWith('---')) return -1
    index += 1
  }

  while (index < lines.length) {
    const line = lines[index].trim()
    if (!line) {
      index += 1
      continue
    }
    if (line.startsWith('---')) return -1
    return index
  }
  return -1
}

export function parseEventNameFromEventNote(text) {
  const lines = String(text || '').split(/\r?\n/)
  const index = findEventNameLineIndex(lines)
  return index === -1 ? '' : lines[index].trim()
}

export function replaceEventNameInEventNote(text, eventName) {
  const lines = String(text || '').split(/\r?\n/)
  const index = findEventNameLineIndex(lines)
  if (index === -1) {
    const separator = lines.findIndex((line) => line.trim().startsWith('---'))
    if (separator === -1) return text
    const beforeSeparator = lines.slice(0, separator)
    while (beforeSeparator.length && !beforeSeparator[beforeSeparator.length - 1].trim()) {
      beforeSeparator.pop()
    }
    return [
      ...beforeSeparator,
      '',
      eventName || '',
      '',
      ...lines.slice(separator),
    ].join('\n')
  }
  const nextLines = [...lines]
  nextLines[index] = eventName || ''
  return nextLines.join('\n')
}

export function replaceDevicesInEventNote(text, devices) {
  const lines = String(text || '').split(/\r?\n/)
  const start = lines.findIndex((line) => line.trim().toLowerCase() === '设备id：' || line.trim().toLowerCase() === '设备id:')
  if (start === -1) return text

  let end = start + 1
  while (end < lines.length) {
    const line = lines[end].trim()
    if (!line) {
      end += 1
      break
    }
    if (line.startsWith('线索ioc') || line.startsWith('银狐-') || line.startsWith('---')) break
    end += 1
  }

  return [
    ...lines.slice(0, start + 1),
    ...uniqueDevices(devices),
    ...lines.slice(end),
  ].join('\n')
}

export function updateEventNoteDevicesForTagChange({
  text,
  selectedTags,
  previousSelectedTags = [],
  tagDeviceMap,
  insertedByTag = {},
}) {
  const selected = new Set(selectedTags || [])
  const previous = new Set(previousSelectedTags || [])
  const addedTags = [...selected].filter((tag) => !previous.has(tag))
  const removedTags = [...previous].filter((tag) => !selected.has(tag))

  let devices = parseDevicesFromEventNote(text)
  const nextInsertedByTag = { ...insertedByTag }

  for (const tag of removedTags) {
    const inserted = new Set(nextInsertedByTag[tag] || [])
    devices = devices.filter((device) => !inserted.has(device))
    delete nextInsertedByTag[tag]
  }

  const existing = new Set(devices)
  for (const tag of addedTags) {
    const inserted = []
    for (const device of uniqueDevices(tagDeviceMap[tag] || [])) {
      if (existing.has(device)) continue
      existing.add(device)
      devices.push(device)
      inserted.push(device)
    }
    nextInsertedByTag[tag] = inserted
  }

  return {
    text: replaceDevicesInEventNote(text, devices),
    insertedByTag: nextInsertedByTag,
  }
}
