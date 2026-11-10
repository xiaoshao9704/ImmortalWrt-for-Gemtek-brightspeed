#!/usr/bin/env python3
"""Run the prepared Airoha IRQ handler with host stubs; no device is accessed."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument('--source', type=Path, required=True, help='prepared Linux tree')
ARGS, REST = PARSER.parse_known_args()
DRIVER = ARGS.source / 'drivers/net/ethernet/airoha'
MATCH = re.search(r'^static irqreturn_t airoha_irq_handler\(.*?^\}',
                  (DRIVER / 'airoha_eth.c').read_text(), re.M | re.S)
if not MATCH:
    raise SystemExit('Cannot extract production airoha_irq_handler')
HANDLER = MATCH.group()

STUBS = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define BIT(n) (1U << (n))
#define GENMASK(h, l) ((~0U >> (31 - (h))) & (~0U << (l)))
#define __ffs(v) __builtin_ctz(v)
#define ARRAY_SIZE(v) (sizeof(v) / sizeof((v)[0]))
#include "airoha_regs.h"
typedef uint32_t u32;
typedef int irqreturn_t;
enum { IRQ_NONE, IRQ_HANDLED };
enum { QDMA_INT_REG_IDX0, QDMA_INT_REG_IDX1, QDMA_INT_REG_IDX2 };
enum { DEV_STATE_INITIALIZED };
struct napi_struct { unsigned int scheduled; };
struct queue { unsigned int ndesc; struct napi_struct napi; };
struct eth { unsigned long state; void *dev; };
struct airoha_qdma { struct eth *eth; struct queue q_rx[32], q_tx_irq[2]; };
struct airoha_irq_bank { struct airoha_qdma *qdma; u32 irqmask[5]; };
static u32 status[0x800 / 4], disabled[5];
static int test_bit(int bit, unsigned long *v) { return !!(*v & BIT(bit)); }
static u32 airoha_qdma_rr(struct airoha_qdma *q, unsigned int reg) { return status[reg / 4]; }
static void airoha_qdma_wr(struct airoha_qdma *q, unsigned int reg, u32 v) { status[reg / 4] &= ~v; }
static void airoha_qdma_irq_disable(struct airoha_irq_bank *b, int reg, u32 mask) { disabled[reg] |= mask; }
static void napi_schedule(struct napi_struct *napi) { napi->scheduled++; }
#define dev_warn_ratelimited(...) ((void)0)
'''

MAIN = r'''
static int run_case(unsigned int queue, int starve, int done, int enabled, int active, int initialized)
{
    struct eth eth = { .state = initialized ? BIT(DEV_STATE_INITIALIZED) : 0 };
    struct airoha_qdma qdma = { .eth = &eth };
    struct airoha_irq_bank bank = { .qdma = &qdma };
    unsigned int reg = queue < 16 ? 1 : 2;
    unsigned int dbit = queue % 16, sbit = dbit + 16;
    unsigned int expected = enabled && active && initialized && (starve || done);
    memset(status, 0, sizeof(status)); memset(disabled, 0, sizeof(disabled));
    qdma.q_rx[queue].ndesc = active ? 128 : 0;
    bank.irqmask[reg] = enabled ? BIT(dbit) | BIT(sbit) : 0;
    status[REG_INT_STATUS(reg) / 4] = (starve ? BIT(sbit) : 0) | (done ? BIT(dbit) : 0);
    int result = airoha_irq_handler(0, &bank);
    if (result != (initialized ? IRQ_HANDLED : IRQ_NONE)) return 1;
    for (unsigned int i = 0; i < 32; i++)
        if (qdma.q_rx[i].napi.scheduled != (i == queue ? expected : 0)) return 2;
    if (disabled[reg] & BIT(sbit)) return 3; /* starvation IRQ must remain enabled */
    if (!!(disabled[reg] & BIT(dbit)) != !!(done && enabled && initialized)) return 4;
    if (qdma.q_tx_irq[0].napi.scheduled || qdma.q_tx_irq[1].napi.scheduled) return 5;
    return 0;
}
int main(void)
{
    unsigned int cases = 0;
    for (unsigned int q = 0; q < 32; q++)
    for (int s = 0; s <= 1; s++)
    for (int d = 0; d <= 1; d++)
    for (int e = 0; e <= 1; e++)
    for (int a = 0; a <= 1; a++)
    for (int i = 0; i <= 1; i++) {
        int err = run_case(q, s, d, e, a, i);
        if (err) { fprintf(stderr, "FAIL queue=%u starve=%d done=%d enabled=%d active=%d initialized=%d error=%d\n", q,s,d,e,a,i,err); return 1; }
        cases++;
    }
    printf("PASS %u IRQ scenarios\n", cases);
    return 0;
}
'''


class StarvationTests(unittest.TestCase):
    def run_handler(self, handler):
        with tempfile.TemporaryDirectory() as tmp:
            src, binary = Path(tmp) / 'irq.c', Path(tmp) / 'irq'
            src.write_text(STUBS + handler + MAIN)
            subprocess.run(['cc', '-std=gnu11', '-O2', '-Wall', '-Werror',
                            '-Wno-sign-compare', '-I', str(DRIVER), str(src), '-o', str(binary)],
                           capture_output=True, text=True, check=True)
            return subprocess.run([str(binary)], capture_output=True, text=True)

    def test_production_handler(self):
        result = self.run_handler(HANDLER)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'PASS 1024 IRQ scenarios')

    def test_rejects_missing_starvation_wakeup(self):
        self.assertIn('rx_intr_mask |= rx_starve;', HANDLER)
        mutant = HANDLER.replace('rx_intr_mask |= rx_starve;', '(void)rx_starve;')
        result = self.run_handler(mutant)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FAIL queue=0 starve=1', result.stderr)

    def test_rejects_wrong_high_bank_shift(self):
        term = '(intr[2] & RX_NO_CPU_DSCP_HIGH_INT_MASK)'
        self.assertIn(term, HANDLER)
        mutant = HANDLER.replace(term, '(' + term + ' >> 16)')
        result = self.run_handler(mutant)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FAIL queue=16 starve=1', result.stderr)


if __name__ == '__main__':
    unittest.main(argv=[__file__, *REST])
