#!/usr/bin/env node

// gbit-container — Modern native process orchestrator (zero Docker/Podman)
// Node.js entry point: delegates to the Python CLI

const { spawn, spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

// Resolve the project root (parent of bin/)
const PROJECT_ROOT = path.resolve(__dirname, '..');

/**
 * Find a working Python executable.
 *
 * Important for Windows:
 * - "python3" may point to the Microsoft Store alias.
 * - "python" may point to the real Python installation.
 * - We therefore TEST the executable instead of trusting its name.
 */
function findPython() {
  const candidates = [];

  const isWindows = process.platform === 'win32';

  // Virtual environment
  if (process.env.VIRTUAL_ENV) {
    if (isWindows) {
      candidates.push(
        path.join(process.env.VIRTUAL_ENV, 'Scripts', 'python.exe')
      );
    } else {
      candidates.push(
        path.join(process.env.VIRTUAL_ENV, 'bin', 'python')
      );
    }
  }

  // Conda environment
  if (process.env.CONDA_PREFIX) {
    candidates.push(
      path.join(
        process.env.CONDA_PREFIX,
        isWindows ? 'python.exe' : 'bin/python'
      )
    );
  }

  // Windows: prefer "python" before "python3"
  // because python3 can be the Microsoft Store alias.
  if (isWindows) {
    candidates.push('python');
    candidates.push('python3');

    // Common real Python installation locations
    candidates.push(
      'C:\\Python314\\python.exe',
      'C:\\Python313\\python.exe',
      'C:\\Python312\\python.exe',
      'C:\\Python311\\python.exe'
    );
  } else {
    candidates.push('python3');
    candidates.push('python');
  }

  return candidates;
}

/**
 * Check whether a candidate really launches Python.
 */
function isWorkingPython(candidate) {
  try {
    let executable = candidate;

    // If this is a direct path, verify that the file exists.
    if (path.isAbsolute(candidate)) {
      if (!fs.existsSync(candidate)) {
        return false;
      }

      executable = candidate;
    }

    const result = spawnSync(
      executable,
      ['--version'],
      {
        stdio: 'pipe',
        windowsHide: true,
        timeout: 5000,
        encoding: 'utf8'
      }
    );

    if (result.error) {
      return false;
    }

    if (result.status !== 0) {
      return false;
    }

    const output = `${result.stdout || ''}${result.stderr || ''}`;

    return /^Python\s+3\./i.test(output.trim());
  } catch (_) {
    return false;
  }
}

/**
 * Determine a working Python binary.
 */
function resolvePython() {
  const candidates = findPython();

  for (const candidate of candidates) {
    if (isWorkingPython(candidate)) {
      return candidate;
    }
  }

  return null;
}

const pythonBin = resolvePython();

if (!pythonBin) {
  console.error('');
  console.error('Error: Python 3 is required but was not found.');
  console.error('');
  console.error('GBit Container requires Python 3.9 or newer.');
  console.error('');
  console.error('Please make sure Python is installed and available in PATH.');
  console.error('');
  process.exit(1);
}

// Show which Python executable is being used when debugging is useful.
if (process.env.GBIT_DEBUG === '1') {
  console.error(`[GBIT] Python: ${pythonBin}`);
  console.error(`[GBIT] Project root: ${PROJECT_ROOT}`);
}

// Forward the current working directory.
const env = Object.assign({}, process.env, {
  GBIT_CWD: process.cwd()
});

// Spawn the Python CLI and forward all stdio.
const child = spawn(
  pythonBin,
  ['-m', 'gbit_container.cli.main', ...process.argv.slice(2)],
  {
    cwd: PROJECT_ROOT,
    env: env,
    stdio: 'inherit',
    windowsHide: true
  }
);

child.on('exit', (code, signal) => {
  if (signal) {
    process.exit(1);
  }

  process.exit(code ?? 0);
});

child.on('error', (err) => {
  console.error('Failed to start gbit-container:', err.message);
  process.exit(1);
});

