package audio

import (
	"bytes"
	"encoding/binary"
	"io"
)

func BytesToInt16(data []byte) []int16 {
	if len(data)%2 != 0 {
		data = append(data, 0)
	}

	ints := make([]int16, len(data)/2)
	for i := 0; i < len(ints); i++ {
		ints[i] = int16(binary.LittleEndian.Uint16(data[i*2 : i*2+2]))
	}

	return ints
}

// ReadInt16 从一个 io.Reader 中读取 int16
func ReadInt16(buff *bytes.Buffer) (int16, error) {
	if buff.Len() < 2 {
		return 0, io.EOF
	}

	lowByte, _ := buff.ReadByte()
	highByte, _ := buff.ReadByte()

	// 将高位字节左移8位，然后与低位字节进行 "或" 运算
	// 这就将两个 8 位的 byte 合并成了一个 16 位的 int16
	val := int16(lowByte) | (int16(highByte) << 8)

	return val, nil
}
