import test from 'node:test';import assert from 'node:assert/strict';
import {textFrames} from '../protocol.js';
test('large Unicode selection survives ordered IPC frames',()=>{const source='Việt Nam 👋 '.repeat(15000);const frames=textFrames(source);assert.equal(frames.join(''),source);assert.ok(frames.length>1);assert.ok(frames.every(f=>new TextEncoder().encode(f).length<=65536));});
