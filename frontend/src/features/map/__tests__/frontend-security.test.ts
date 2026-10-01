import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    return statSync(path).isDirectory() ? sourceFiles(path) : [path];
  });
}

describe('frontend credential boundary', () => {
  it('does not reference a backend Goong REST credential', () => {
    const forbiddenName = ['VITE', 'GOONG', 'API', 'KEY'].join('_');
    const files = sourceFiles(join(process.cwd(), 'src'));
    const occurrences = files.filter((file) => readFileSync(file, 'utf8').includes(forbiddenName));

    expect(occurrences).toEqual([]);
  });
});
