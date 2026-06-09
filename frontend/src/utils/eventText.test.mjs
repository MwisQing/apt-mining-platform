import assert from 'node:assert/strict'
import {
  buildEventNote,
  defaultEventName,
  parseEventNameFromEventNote,
  parseIocFromEventNote,
  parseDevicesFromEventNote,
  replaceEventNameInEventNote,
  updateEventNoteDevicesForTagChange,
} from './eventText.js'

const fixedDate = new Date(2026, 4, 29)

assert.equal(defaultEventName(fixedDate), '银狐-2026年5月29日')

const note = buildEventNote({
  ioc: '192.238.132.17:30088',
  devices: ['902179e8bb8070628c0f4c0e6908c9a6', '725BF3B705755F50DC137C74E8657B0C'],
  eventName: defaultEventName(fixedDate),
})

assert.deepEqual(parseDevicesFromEventNote(note), [
  '902179E8BB8070628C0F4C0E6908C9A6',
  '725BF3B705755F50DC137C74E8657B0C',
])

assert.deepEqual(parseIocFromEventNote(note), {
  target: '192.238.132.17',
  port: '30088',
})

assert.equal(parseEventNameFromEventNote(note), '银狐-2026年5月29日')

const editedEventNameNote = note.replace('银狐-2026年5月29日', '银狐事件-2026年6月1日')
assert.equal(parseEventNameFromEventNote(editedEventNameNote), '银狐事件-2026年6月1日')

const renamedNote = replaceEventNameInEventNote(note, '银狐事件-2026年6月1日')
assert.equal(parseEventNameFromEventNote(renamedNote), '银狐事件-2026年6月1日')
assert.deepEqual(parseIocFromEventNote(renamedNote), {
  target: '192.238.132.17',
  port: '30088',
})
assert.deepEqual(parseDevicesFromEventNote(renamedNote), [
  '902179E8BB8070628C0F4C0E6908C9A6',
  '725BF3B705755F50DC137C74E8657B0C',
])

const missingTitleNote = note.replace('银狐-2026年5月29日\n\n', '')
const restoredTitleNote = replaceEventNameInEventNote(missingTitleNote, '银狐事件-2026年6月1日')
assert.equal(parseEventNameFromEventNote(restoredTitleNote), '银狐事件-2026年6月1日')

assert.deepEqual(parseIocFromEventNote('线索ioc：[2001:db8::1]:443'), {
  target: '2001:db8::1',
  port: '443',
})

const tagDeviceMap = {
  '01排查成功': [
    '902179E8BB8070628C0F4C0E6908C9A6',
    '725BF3B705755F50DC137C74E8657B0C',
  ],
  '02重点设备': [
    'D0C66BDB6991B0625336967F0B5E626C',
  ],
}

const withManual = buildEventNote({
  ioc: '192.238.132.17:30088',
  devices: ['MANUAL_DEVICE'],
  eventName: defaultEventName(fixedDate),
})

const selectedResult = updateEventNoteDevicesForTagChange({
  text: withManual,
  selectedTags: ['01排查成功', '02重点设备'],
  previousSelectedTags: [],
  tagDeviceMap,
})
const selected = selectedResult.text

assert.deepEqual(parseDevicesFromEventNote(selected), [
  'MANUAL_DEVICE',
  '902179E8BB8070628C0F4C0E6908C9A6',
  '725BF3B705755F50DC137C74E8657B0C',
  'D0C66BDB6991B0625336967F0B5E626C',
])

const unselectedResult = updateEventNoteDevicesForTagChange({
  text: selected,
  selectedTags: ['02重点设备'],
  previousSelectedTags: ['01排查成功', '02重点设备'],
  tagDeviceMap,
  insertedByTag: selectedResult.insertedByTag,
})
const unselected = unselectedResult.text

assert.deepEqual(parseDevicesFromEventNote(unselected), [
  'MANUAL_DEVICE',
  'D0C66BDB6991B0625336967F0B5E626C',
])

const currentDeviceNote = buildEventNote({
  ioc: '192.238.132.17:30088',
  devices: ['902179E8BB8070628C0F4C0E6908C9A6'],
  eventName: defaultEventName(fixedDate),
})

const addCurrentDeviceTag = updateEventNoteDevicesForTagChange({
  text: currentDeviceNote,
  selectedTags: ['01排查成功'],
  previousSelectedTags: [],
  tagDeviceMap,
})

const removedAgain = updateEventNoteDevicesForTagChange({
  text: addCurrentDeviceTag.text,
  selectedTags: [],
  previousSelectedTags: ['01排查成功'],
  tagDeviceMap,
  insertedByTag: addCurrentDeviceTag.insertedByTag,
}).text

assert.deepEqual(parseDevicesFromEventNote(removedAgain), [
  '902179E8BB8070628C0F4C0E6908C9A6',
])
