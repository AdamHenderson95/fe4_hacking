// Generated from LakeSnes cpu.c opcode comments (MIT). Do not edit.
#ifndef RC_OPS_H
#define RC_OPS_H

enum { M_ABL, M_ABS, M_ABX, M_ABX_W, M_ABY, M_ABY_W, M_ALX, M_BM, M_DP, M_DPX, M_DPY, M_IAL, M_IAX, M_IDL, M_IDP, M_IDX, M_IDY, M_IDY_W, M_ILY, M_IMM16, M_IMM8, M_IMM_M, M_IMM_X, M_IMP, M_IND, M_ISY, M_REL, M_RLL, M_SR, M_COUNT };
enum { O_ADC, O_AND, O_ASL, O_ASLA, O_BCC, O_BCS, O_BEQ, O_BIT, O_BITI, O_BMI, O_BNE, O_BPL, O_BRA, O_BRK, O_BRL, O_BVC, O_BVS, O_CLC, O_CLD, O_CLI, O_CLV, O_CMP, O_COP, O_CPX, O_CPY, O_DEC, O_DECA, O_DEX, O_DEY, O_EOR, O_INC, O_INCA, O_INX, O_INY, O_JML, O_JMP, O_JSL, O_JSR, O_LDA, O_LDX, O_LDY, O_LSR, O_LSRA, O_MVN, O_MVP, O_NOP, O_ORA, O_PEA, O_PEI, O_PER, O_PHA, O_PHB, O_PHD, O_PHK, O_PHP, O_PHX, O_PHY, O_PLA, O_PLB, O_PLD, O_PLP, O_PLX, O_PLY, O_REP, O_ROL, O_ROLA, O_ROR, O_RORA, O_RTI, O_RTL, O_RTS, O_SBC, O_SEC, O_SED, O_SEI, O_SEP, O_STA, O_STP, O_STX, O_STY, O_STZ, O_TAX, O_TAY, O_TCD, O_TCS, O_TDC, O_TRB, O_TSB, O_TSC, O_TSX, O_TXA, O_TXS, O_TXY, O_TYA, O_TYX, O_WAI, O_WDM, O_XBA, O_XCE, O_COUNT };
static const char* const rc_opNames[O_COUNT] = { "adc", "and", "asl", "asla", "bcc", "bcs", "beq", "bit", "biti", "bmi", "bne", "bpl", "bra", "brk", "brl", "bvc", "bvs", "clc", "cld", "cli", "clv", "cmp", "cop", "cpx", "cpy", "dec", "deca", "dex", "dey", "eor", "inc", "inca", "inx", "iny", "jml", "jmp", "jsl", "jsr", "lda", "ldx", "ldy", "lsr", "lsra", "mvn", "mvp", "nop", "ora", "pea", "pei", "per", "pha", "phb", "phd", "phk", "php", "phx", "phy", "pla", "plb", "pld", "plp", "plx", "ply", "rep", "rol", "rola", "ror", "rora", "rti", "rtl", "rts", "sbc", "sec", "sed", "sei", "sep", "sta", "stp", "stx", "sty", "stz", "tax", "tay", "tcd", "tcs", "tdc", "trb", "tsb", "tsc", "tsx", "txa", "txs", "txy", "tya", "tyx", "wai", "wdm", "xba", "xce" };
static const unsigned char rc_opTab[256][2] = {
  {O_BRK,M_IMM8}, {O_ORA,M_IDX}, {O_COP,M_IMM8}, {O_ORA,M_SR}, {O_TSB,M_DP}, {O_ORA,M_DP}, {O_ASL,M_DP}, {O_ORA,M_IDL},
  {O_PHP,M_IMP}, {O_ORA,M_IMM_M}, {O_ASLA,M_IMP}, {O_PHD,M_IMP}, {O_TSB,M_ABS}, {O_ORA,M_ABS}, {O_ASL,M_ABS}, {O_ORA,M_ABL},
  {O_BPL,M_REL}, {O_ORA,M_IDY}, {O_ORA,M_IDP}, {O_ORA,M_ISY}, {O_TRB,M_DP}, {O_ORA,M_DPX}, {O_ASL,M_DPX}, {O_ORA,M_ILY},
  {O_CLC,M_IMP}, {O_ORA,M_ABY}, {O_INCA,M_IMP}, {O_TCS,M_IMP}, {O_TRB,M_ABS}, {O_ORA,M_ABX}, {O_ASL,M_ABX_W}, {O_ORA,M_ALX},
  {O_JSR,M_ABS}, {O_AND,M_IDX}, {O_JSL,M_ABL}, {O_AND,M_SR}, {O_BIT,M_DP}, {O_AND,M_DP}, {O_ROL,M_DP}, {O_AND,M_IDL},
  {O_PLP,M_IMP}, {O_AND,M_IMM_M}, {O_ROLA,M_IMP}, {O_PLD,M_IMP}, {O_BIT,M_ABS}, {O_AND,M_ABS}, {O_ROL,M_ABS}, {O_AND,M_ABL},
  {O_BMI,M_REL}, {O_AND,M_IDY}, {O_AND,M_IDP}, {O_AND,M_ISY}, {O_BIT,M_DPX}, {O_AND,M_DPX}, {O_ROL,M_DPX}, {O_AND,M_ILY},
  {O_SEC,M_IMP}, {O_AND,M_ABY}, {O_DECA,M_IMP}, {O_TSC,M_IMP}, {O_BIT,M_ABX}, {O_AND,M_ABX}, {O_ROL,M_ABX_W}, {O_AND,M_ALX},
  {O_RTI,M_IMP}, {O_EOR,M_IDX}, {O_WDM,M_IMM8}, {O_EOR,M_SR}, {O_MVP,M_BM}, {O_EOR,M_DP}, {O_LSR,M_DP}, {O_EOR,M_IDL},
  {O_PHA,M_IMP}, {O_EOR,M_IMM_M}, {O_LSRA,M_IMP}, {O_PHK,M_IMP}, {O_JMP,M_ABS}, {O_EOR,M_ABS}, {O_LSR,M_ABS}, {O_EOR,M_ABL},
  {O_BVC,M_REL}, {O_EOR,M_IDY}, {O_EOR,M_IDP}, {O_EOR,M_ISY}, {O_MVN,M_BM}, {O_EOR,M_DPX}, {O_LSR,M_DPX}, {O_EOR,M_ILY},
  {O_CLI,M_IMP}, {O_EOR,M_ABY}, {O_PHY,M_IMP}, {O_TCD,M_IMP}, {O_JML,M_ABL}, {O_EOR,M_ABX}, {O_LSR,M_ABX_W}, {O_EOR,M_ALX},
  {O_RTS,M_IMP}, {O_ADC,M_IDX}, {O_PER,M_RLL}, {O_ADC,M_SR}, {O_STZ,M_DP}, {O_ADC,M_DP}, {O_ROR,M_DP}, {O_ADC,M_IDL},
  {O_PLA,M_IMP}, {O_ADC,M_IMM_M}, {O_RORA,M_IMP}, {O_RTL,M_IMP}, {O_JMP,M_IND}, {O_ADC,M_ABS}, {O_ROR,M_ABS}, {O_ADC,M_ABL},
  {O_BVS,M_REL}, {O_ADC,M_IDY}, {O_ADC,M_IDP}, {O_ADC,M_ISY}, {O_STZ,M_DPX}, {O_ADC,M_DPX}, {O_ROR,M_DPX}, {O_ADC,M_ILY},
  {O_SEI,M_IMP}, {O_ADC,M_ABY}, {O_PLY,M_IMP}, {O_TDC,M_IMP}, {O_JMP,M_IAX}, {O_ADC,M_ABX}, {O_ROR,M_ABX_W}, {O_ADC,M_ALX},
  {O_BRA,M_REL}, {O_STA,M_IDX}, {O_BRL,M_RLL}, {O_STA,M_SR}, {O_STY,M_DP}, {O_STA,M_DP}, {O_STX,M_DP}, {O_STA,M_IDL},
  {O_DEY,M_IMP}, {O_BITI,M_IMM_M}, {O_TXA,M_IMP}, {O_PHB,M_IMP}, {O_STY,M_ABS}, {O_STA,M_ABS}, {O_STX,M_ABS}, {O_STA,M_ABL},
  {O_BCC,M_REL}, {O_STA,M_IDY_W}, {O_STA,M_IDP}, {O_STA,M_ISY}, {O_STY,M_DPX}, {O_STA,M_DPX}, {O_STX,M_DPY}, {O_STA,M_ILY},
  {O_TYA,M_IMP}, {O_STA,M_ABY_W}, {O_TXS,M_IMP}, {O_TXY,M_IMP}, {O_STZ,M_ABS}, {O_STA,M_ABX_W}, {O_STZ,M_ABX_W}, {O_STA,M_ALX},
  {O_LDY,M_IMM_X}, {O_LDA,M_IDX}, {O_LDX,M_IMM_X}, {O_LDA,M_SR}, {O_LDY,M_DP}, {O_LDA,M_DP}, {O_LDX,M_DP}, {O_LDA,M_IDL},
  {O_TAY,M_IMP}, {O_LDA,M_IMM_M}, {O_TAX,M_IMP}, {O_PLB,M_IMP}, {O_LDY,M_ABS}, {O_LDA,M_ABS}, {O_LDX,M_ABS}, {O_LDA,M_ABL},
  {O_BCS,M_REL}, {O_LDA,M_IDY}, {O_LDA,M_IDP}, {O_LDA,M_ISY}, {O_LDY,M_DPX}, {O_LDA,M_DPX}, {O_LDX,M_DPY}, {O_LDA,M_ILY},
  {O_CLV,M_IMP}, {O_LDA,M_ABY}, {O_TSX,M_IMP}, {O_TYX,M_IMP}, {O_LDY,M_ABX}, {O_LDA,M_ABX}, {O_LDX,M_ABY}, {O_LDA,M_ALX},
  {O_CPY,M_IMM_X}, {O_CMP,M_IDX}, {O_REP,M_IMM8}, {O_CMP,M_SR}, {O_CPY,M_DP}, {O_CMP,M_DP}, {O_DEC,M_DP}, {O_CMP,M_IDL},
  {O_INY,M_IMP}, {O_CMP,M_IMM_M}, {O_DEX,M_IMP}, {O_WAI,M_IMP}, {O_CPY,M_ABS}, {O_CMP,M_ABS}, {O_DEC,M_ABS}, {O_CMP,M_ABL},
  {O_BNE,M_REL}, {O_CMP,M_IDY}, {O_CMP,M_IDP}, {O_CMP,M_ISY}, {O_PEI,M_DP}, {O_CMP,M_DPX}, {O_DEC,M_DPX}, {O_CMP,M_ILY},
  {O_CLD,M_IMP}, {O_CMP,M_ABY}, {O_PHX,M_IMP}, {O_STP,M_IMP}, {O_JML,M_IAL}, {O_CMP,M_ABX}, {O_DEC,M_ABX_W}, {O_CMP,M_ALX},
  {O_CPX,M_IMM_X}, {O_SBC,M_IDX}, {O_SEP,M_IMM8}, {O_SBC,M_SR}, {O_CPX,M_DP}, {O_SBC,M_DP}, {O_INC,M_DP}, {O_SBC,M_IDL},
  {O_INX,M_IMP}, {O_SBC,M_IMM_M}, {O_NOP,M_IMP}, {O_XBA,M_IMP}, {O_CPX,M_ABS}, {O_SBC,M_ABS}, {O_INC,M_ABS}, {O_SBC,M_ABL},
  {O_BEQ,M_REL}, {O_SBC,M_IDY}, {O_SBC,M_IDP}, {O_SBC,M_ISY}, {O_PEA,M_IMM16}, {O_SBC,M_DPX}, {O_INC,M_DPX}, {O_SBC,M_ILY},
  {O_SED,M_IMP}, {O_SBC,M_ABY}, {O_PLX,M_IMP}, {O_XCE,M_IMP}, {O_JSR,M_IAX}, {O_SBC,M_ABX}, {O_INC,M_ABX_W}, {O_SBC,M_ALX},
};

// instruction length given m/x flags (1 = 8-bit)
static inline int rc_opLen(unsigned char opc, int m, int x) {
  switch(rc_opTab[opc][1]) {
    case M_IMP: return 1;
    case M_IMM_M: return m ? 2 : 3;
    case M_IMM_X: return x ? 2 : 3;
    case M_IMM8: case M_DP: case M_DPX: case M_DPY: case M_IDP: case M_IDX: case M_IDY: case M_IDY_W:
    case M_IDL: case M_ILY: case M_SR: case M_ISY: case M_REL: return 2;
    case M_IMM16: case M_ABS: case M_ABX: case M_ABX_W: case M_ABY: case M_ABY_W: case M_IND: case M_IAX:
    case M_IAL: case M_RLL: case M_BM: return 3;
    case M_ABL: case M_ALX: return 4;
  }
  return 1;
}

// does this opcode end a compiled block? (control flow, or flags become unknown)
static inline int rc_opEndsBlock(unsigned char opc) {
  switch(opc) {
    case 0x00: case 0x02: case 0x20: case 0x22: case 0x28: case 0x40: case 0x44: case 0x4c: case 0x54:
    case 0x5c: case 0x60: case 0x6b: case 0x6c: case 0x7c: case 0x80: case 0x82: case 0xcb: case 0xdb:
    case 0xdc: case 0xfb: case 0xfc:
    case 0x10: case 0x30: case 0x50: case 0x70: case 0x90: case 0xb0: case 0xd0: case 0xf0:
      return 1;
  }
  return 0;
}
#endif
