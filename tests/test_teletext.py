import contextlib
import io
import os
import re
import tempfile
import unittest

from teletext import decdld, font, imageconv, page as P, render, sixel
from teletext.feeds import (article, builder, rss, sources, ukmap,
                            weather)
from tests.sixel_decode import decode
from tests.decdld_decode import decode as decode_font


class FontTest(unittest.TestCase):
    def test_full_charset(self):
        self.assertEqual(len(font.ASCII_GLYPHS), 96)
        for code in range(0x20, 0x80):
            self.assertIn(code, font.ENGLISH_GLYPHS)
            self.assertEqual(len(font.ENGLISH_GLYPHS[code]), font.CELL_H)

    def test_mosaic_bit_order(self):
        blank = font.char_bitmap(0x20, graphics=True)
        self.assertEqual(sum(blank), 0)
        full = font.char_bitmap(0x7F, graphics=True)
        self.assertTrue(all(r == 0x3F for r in full))
        # 0x60 is bit 5 only: the bottom-right block
        br = font.char_bitmap(0x60, graphics=True)
        self.assertEqual(sum(br[:6]), 0)
        self.assertEqual(br[6], 0b000111)

    def test_separated_leaves_a_gap(self):
        solid = font.char_bitmap(0x7F, graphics=True, sep=False)
        gapped = font.char_bitmap(0x7F, graphics=True, sep=True)
        self.assertNotEqual(solid, gapped)
        self.assertEqual(gapped[2], 0)          # bottom row of each block

    def test_capitals_stay_alphanumeric_in_graphics(self):
        self.assertEqual(font.char_bitmap(0x41, graphics=True),
                         font.char_bitmap(0x41, graphics=False))


class PageTest(unittest.TestCase):
    def test_markup_round_trip(self):
        line = '{red}{double}HELLO {gcyan}{sep}world'
        codes = P.encode_line(line)
        self.assertEqual(codes[0], P.ALPHA_RED)
        self.assertEqual(codes[1], P.DOUBLE_HEIGHT)
        self.assertEqual(P.decode_line(codes), line)

    def test_mosaic_cell_token(self):
        """{##.#..} is one cell with its six blocks in reading order."""
        codes = P.encode_line('{gred}{....##}{######}')
        self.assertEqual(len(codes), 3)
        self.assertEqual(P.unpack_mosaic(codes[1]), 0b110000)
        self.assertEqual(P.unpack_mosaic(codes[2]), 0b111111)

    def test_mosaic_code_inverse(self):
        for v in range(64):
            self.assertEqual(P.unpack_mosaic(P.mosaic_code(v)), v)

    def test_page_serialises(self):
        pg = P.parse('!title T\n{yellow}Hi\n')
        text = P.serialize(pg)
        again = P.parse(text)
        self.assertEqual(again.rows, pg.rows)
        self.assertEqual(again.title, 'T')

    def test_row_is_truncated_to_40(self):
        pg = P.parse('x' * 60 + '\n', warn=False)
        self.assertEqual(len(pg.rows[0]), P.COLS)

    def test_internal_meta_not_written(self):
        pg = P.Page()
        pg.meta['_dir'] = '/tmp'
        pg.meta['link'] = 'http://x'
        text = P.serialize(pg)
        self.assertNotIn('_dir', text)
        self.assertIn('link', text)

    def test_tti_round_trip(self):
        pg = P.parse('{red}Hello {gcyan}world\n')
        again = P.load_tti(P.dump_tti(pg))
        self.assertEqual(again.rows[0], pg.rows[0])

    def test_graphic_block(self):
        pg = P.parse('!graphic row=0 col=1 colour=cyan\n##\n##\n##\n!endgraphic\n')
        self.assertEqual(pg.rows[0][0], P.GRAPHICS_CYAN)
        self.assertEqual(pg.rows[0][1], P.mosaic_code(0x3F))


class RenderTest(unittest.TestCase):
    def test_bitmap_size(self):
        pg = P.Page()
        self.assertEqual((render.render(pg, 1).width,
                          render.render(pg, 1).height), (240, 225))
        bm = render.render(pg, 2)
        self.assertEqual((bm.width, bm.height), (480, 450))

    def test_colour_is_set_after(self):
        cells = render.row_cells(P.encode_line('{red}AB'))
        self.assertEqual(cells[0].fg, 7)        # the attribute cell itself
        self.assertEqual(cells[1].fg, 1)
        self.assertEqual(cells[2].fg, 1)

    def test_background_is_set_at(self):
        cells = render.row_cells(P.encode_line('{blue}{newbg}X'))
        self.assertEqual(cells[1].bg, 4)        # new background acts at once
        self.assertEqual(cells[2].bg, 4)

    def test_hold_mosaics(self):
        codes = P.encode_line('{gwhite}{7F}{hold}{gred}X')
        cells = render.row_cells(codes)
        held = cells[3]                         # the colour change cell
        self.assertTrue(held.gfx)
        self.assertEqual(held.code, 0x7F)       # shows the held block

    def test_double_height_consumes_next_row(self):
        pg = P.Page()
        pg.write(0, 0, '{double}A')
        pg.write(1, 0, 'B')                     # hidden by the lower half
        bm = render.render(pg, 1)
        row_b = bm.pix[font.CELL_H * bm.width:(font.CELL_H + 1) * bm.width]
        top = bm.pix[0:bm.width]
        self.assertTrue(any(row_b))             # lower half of the A is drawn
        self.assertTrue(any(top))

    def test_conceal(self):
        pg = P.Page()
        pg.write(0, 0, '{conceal}SECRET')
        self.assertEqual(sum(render.render(pg, 1).pix), 0)
        self.assertNotEqual(sum(render.render(pg, 1, reveal=True).pix), 0)

    def test_flash_off_blanks(self):
        pg = P.Page()
        pg.write(0, 0, '{flash}HI')
        self.assertEqual(sum(render.render(pg, 1, flash_on=False).pix), 0)


class RoundingTest(unittest.TestCase):
    """A real teletext chip fills the corner where a diagonal steps;
    without that, text is a staircase."""

    def test_rounding_fills_diagonal_corners(self):
        plain = font.char_bitmap(0x41)                  # 'A'
        rounded = font.rounded_bitmap(0x41)
        self.assertEqual(len(rounded), font.CELL_H * 2)
        # doubling alone would give each row an even number of set bits
        # per source pixel; rounding adds more
        plain_ink = sum(bin(r).count('1') for r in plain) * 4
        round_ink = sum(bin(r).count('1') for r in rounded)
        self.assertGreater(round_ink, plain_ink)

    def test_mosaics_are_not_rounded(self):
        """Rounding a block graphic would eat its corners."""
        for code in (0x3F, 0x7F, 0x35):
            plain = font.char_bitmap(code, graphics=True)
            rounded = font.rounded_bitmap(code, graphics=True)
            plain_ink = sum(bin(r).count('1') for r in plain) * 4
            self.assertEqual(sum(bin(r).count('1') for r in rounded),
                             plain_ink, 'mosaic %02X was rounded' % code)

    def test_solid_shapes_are_unchanged(self):
        rounded = font.rounded_bitmap(0x7F, graphics=True)
        self.assertTrue(all(r == 0xFFF for r in rounded))

    def test_page_size_is_the_same_either_way(self):
        pg = P.parse('{red}Hello\n')
        a = render.render(pg, 2, rounding=True)
        b = render.render(pg, 2, rounding=False)
        self.assertEqual((a.width, a.height), (b.width, b.height))
        self.assertNotEqual(a.pix, b.pix)

    def test_double_height_still_works_when_rounded(self):
        pg = P.Page()
        pg.write(0, 0, '{double}A')
        bm = render.render(pg, 2, rounding=True)
        ch = font.CELL_H * 2
        top = bm.pix[:bm.width]
        lower = bm.pix[ch * bm.width:(ch + 1) * bm.width]
        self.assertTrue(any(top))
        self.assertTrue(any(lower))     # the bottom half is drawn below


class SoftFontTest(unittest.TestCase):
    """The font is sent once and pages then go as characters, so the
    glyph data has to describe the shapes we meant."""

    def test_header_parameters(self):
        seq = decdld.soft_font(cell=(10, 20))
        params, dscs, glyphs, cell = decode_font(seq)
        self.assertEqual(cell, (10, 20))
        self.assertEqual(params[0], 1)          # font buffer
        self.assertEqual(params[2], 2)          # erase all renditions
        self.assertEqual(params[5], 2)          # full cell
        self.assertEqual(params[7], 0)          # 94-character set
        self.assertEqual(dscs, decdld.ALPHA_DSCS)
        self.assertEqual(len(glyphs), 94)       # 0x21..0x7E

    def test_glyphs_round_trip(self):
        seq = decdld.soft_font(cell=(10, 20))
        _, _, glyphs, _ = decode_font(seq)
        for code in (0x41, 0x67, 0x30, 0x21, 0x7E):
            self.assertEqual(glyphs[code],
                             decdld.glyph_bits(code, 10, 20),
                             'glyph %02X does not survive the round trip'
                             % code)

    def test_mosaic_set_covers_the_full_block(self):
        seq = decdld.soft_font(cell=(10, 20), graphics=True)
        params, dscs, glyphs, _ = decode_font(seq)
        self.assertEqual(params[7], 1)          # 96 characters
        self.assertEqual(dscs, decdld.MOSAIC_DSCS)
        self.assertIn(0x7F, glyphs)             # every block filled
        self.assertTrue(all(r == (1 << 10) - 1 for r in glyphs[0x7F]))
        self.assertIn(0x20, glyphs)             # and the empty one
        self.assertEqual(sum(glyphs[0x20]), 0)

    def test_mosaics_are_drawn_in_the_cell_not_scaled(self):
        """Scaling a 6x9 mosaic puts the block boundaries in the wrong
        place; they are worked out in the cell's own pixels."""
        bits = decdld.mosaic_bits(P.mosaic_code(0x01), 10, 20)   # top-left
        self.assertEqual(bits[0], 0b1111100000)
        self.assertEqual(bits[6], 0)            # nothing below a third

    def test_one_font_serves_every_drawing_path(self):
        """The page renderer, the downloaded soft font and the labels on
        the weather map all draw text; a character has to look the same
        in all three or the service looks assembled from parts."""
        from teletext.feeds import ukmap
        for code in (0x41, 0x67, 0x35, 0x77):
            fitted = font.fitted_bitmap(code, font.CELL_W, font.CELL_H)
            self.assertEqual(decdld.glyph_bits(code, font.CELL_W,
                                               font.CELL_H), fitted,
                             'soft font differs at %02X' % code)
        # the map draws through the same call
        import inspect
        self.assertIn('fitted_bitmap', inspect.getsource(ukmap._text))

    def test_fitting_is_the_rounded_shape_at_its_own_size(self):
        for code in (0x41, 0x73):
            self.assertEqual(
                font.fitted_bitmap(code, font.CELL_W * 2, font.CELL_H * 2),
                font.rounded_bitmap(code))

    def test_strokes_keep_their_weight(self):
        """A downloaded font is one bit deep, so coverage is all there
        is.  Fitting by area keeps a stem the width its proportion asks
        for; sampling the nearest source pixel thins it to one pixel,
        which is what made the soft font look frail next to the page."""
        def nearest(code, cw, ch):
            bits = font.rounded_bitmap(code, 'english')
            out = []
            for y in range(ch):
                row = bits[min(17, y * 18 // ch)]
                v = 0
                for x in range(cw):
                    if (row >> (11 - min(11, x * 12 // cw))) & 1:
                        v |= 1 << (cw - 1 - x)
                out.append(v)
            return out

        def hairline_rows(bits):
            return sum(1 for r in bits if bin(r).count('1') == 1)

        for code, name in ((0x6C, 'l'), (0x54, 'T'), (0x69, 'i')):
            area = hairline_rows(decdld.glyph_bits(code, 10, 20))
            sampled = hairline_rows(nearest(code, 10, 20))
            # an edge row may still come out thin where the 18-row source
            # meets a 20-row cell; a stem should not
            self.assertLessEqual(area, 1, '%s is mostly hairline' % name)
            self.assertGreater(sampled, area,
                               '%s: sampling was no worse, check the test'
                               % name)

    def test_a_thin_stroke_survives_the_fit(self):
        # 'l' is a single column in the source: sampling can drop it
        for cell in ((10, 20), (10, 12), (8, 10)):
            bits = decdld.glyph_bits(0x6C, *cell)
            self.assertTrue(any(bits), 'l vanished at %dx%d' % cell)

    def test_every_glyph_has_ink_at_every_cell_size(self):
        for cell in ((10, 20), (10, 12), (12, 18)):
            for code in range(0x21, 0x7F):
                bits = decdld.glyph_bits(code, *cell)
                self.assertTrue(any(bits),
                                'glyph %02X is blank at %dx%d'
                                % (code, cell[0], cell[1]))

    def test_page_as_text_is_much_smaller(self):
        # a full page: the encoder's solid fill already makes a sparse
        # one cheap, so a fair comparison needs every row used
        pg = P.Page()
        for r in range(P.ROWS):
            pg.write(r, 0, '{yellow}Row %02d of text across the whole page'
                     % r)
        text = decdld.page_text(pg)
        sixel_bytes = len(sixel.encode(render.render(pg, 1.5)))
        self.assertLess(len(text), sixel_bytes / 3,
                        'text %d vs sixel %d' % (len(text), sixel_bytes))

    def test_page_text_layout(self):
        pg = P.Page()
        pg.write(0, 0, '{red}ONE')
        pg.write(1, 0, '{double}TWO')
        text = decdld.page_text(pg)
        self.assertIn('\x1b( ', text)            # G0 designated
        self.assertIn('\x1b) ', text)            # G1 designated
        self.assertIn(decdld.DECDWL, text)       # 40 columns
        self.assertIn(decdld.DECDHL_TOP, text)   # double height
        self.assertIn(decdld.DECDHL_BOTTOM, text)
        self.assertIn('ONE', text)
        self.assertIn('\x1b[0;31;40m', text)     # red on black

    def test_mosaics_switch_to_g1(self):
        pg = P.parse('{gcyan}{7F}{7F}\n')
        text = decdld.page_text(pg)
        self.assertIn(decdld.SO, text)           # shift out to the mosaics
        self.assertTrue(text.rstrip('\x1b[0m').endswith(decdld.SI)
                        or decdld.SI in text)    # and back again

    def test_double_height_takes_two_lines(self):
        pg = P.Page()
        for r in range(4):
            pg.write(r, 0, '{double}R%d' % r)
        text = decdld.page_text(pg, rows=24)
        self.assertEqual(text.count(decdld.DECDHL_TOP),
                         text.count(decdld.DECDHL_BOTTOM))

    def test_row_budget_is_respected(self):
        pg = P.Page()
        for r in range(P.ROWS):
            pg.write(r, 0, 'row %d' % r)
        text = decdld.page_text(pg, rows=24)
        self.assertEqual(text.count('\x1b#'), 24)


class NativeCellTest(unittest.TestCase):
    """A page is drawn in the terminal's own pixels; nothing is
    resampled, so strokes cannot come out a mix of weights."""

    def test_cell_sizes_are_whole_pixels(self):
        self.assertEqual(render.cell_size(1), (6, 9))
        self.assertEqual(render.cell_size(1.5), (9, 14))
        self.assertEqual(render.cell_size(2), (12, 18))
        self.assertEqual(render.cell_size((2, 1)), (12, 9))

    def test_page_is_whole_cells(self):
        pg = P.parse('{red}Hello\n')
        bm = render.render(pg, 1.5)
        self.assertEqual((bm.width, bm.height), (40 * 9, 25 * 14))
        self.assertEqual(len(bm.palette), 8)     # no blended colours

    def test_stems_are_one_weight(self):
        """Every vertical stem is two pixels at 9x14, whichever column
        of the character it stands in."""
        heights = font._share(14, font._ROW_ORDER)
        for ch in 'HIlTmun':
            src = font.char_bitmap(ord(ch))
            bits = font.native_bitmap(ord(ch), 9, 14)
            y = 0
            for sy in range(font.CELL_H):
                pattern = bin(src[sy])[2:].zfill(font.CELL_W)
                plain = ('11' not in pattern and 0 < sy < font.CELL_H - 1
                         and src[sy - 1] == src[sy] == src[sy + 1])
                if plain and src[sy]:
                    row = bin(bits[y])[2:].zfill(9)
                    runs = [len(r) for r in row.split('0') if r]
                    self.assertEqual(set(runs), {2},
                                     '%s row %d: %s' % (ch, sy, row))
                y += heights[sy]

    def test_horizontal_bars_are_one_weight(self):
        """The three bars of E are each one pixel deep at 9x14."""
        bits = font.native_bitmap(ord('E'), 9, 14)
        full = [i for i, r in enumerate(bits) if bin(r).count('1') >= 7]
        self.assertEqual(len(full), 2)           # top and bottom bars
        middle = [i for i, r in enumerate(bits)
                  if bin(r).count('1') >= 6 and i not in full]
        self.assertTrue(middle)

    def test_mosaics_fill_the_cell_at_any_size(self):
        for w, h in ((6, 9), (9, 14), (12, 18), (10, 20)):
            bits = font.native_bitmap(0x7F, w, h, graphics=True)
            self.assertEqual(bits, [(1 << w) - 1] * h)

    def test_separated_mosaics_leave_a_gap(self):
        bits = font.native_bitmap(0x7F, 9, 14, graphics=True, sep=True)
        self.assertEqual(bits[-1], 0)
        self.assertTrue(all(not r & 1 for r in bits))


class SixelTest(unittest.TestCase):
    def _roundtrip(self, bm):
        data = sixel.encode(bm)
        w, h, pixels, palette = decode(data)
        self.assertEqual((w, h), (bm.width, bm.height))
        for y in range(bm.height):
            for x in range(bm.width):
                want = bm.pix[y * bm.width + x]
                got = pixels[y][x]
                self.assertEqual(got, want,
                                 'pixel %d,%d: %r != %r' % (x, y, got, want))
        return palette

    def test_round_trip_page(self):
        pg = P.parse('{red}Hello {gcyan}{7F}{yellow}World\n'
                     '{green}{double}BIG\n')
        bm = render.render(pg, 1)
        palette = self._roundtrip(bm)
        self.assertEqual(palette[1], (255, 0, 0))

    def test_round_trip_odd_height(self):
        # 225 rows is not a multiple of 6: the last band is partial
        bm = render.Bitmap(9, 7)
        for i in range(len(bm.pix)):
            bm.pix[i] = i % 8
        self._roundtrip(bm)

    def test_solid_fill_is_still_pixel_exact(self):
        """The commonest colour in a band is laid down as one run and
        the rest painted over it; sixel passes overwrite, so the result
        has to come back identical."""
        pg = P.parse('{red}Hello {gcyan}{7F}{yellow}World\n'
                     '{green}{double}BIG\n{white}more text here\n')
        bm = render.render(pg, 1.5)
        self._roundtrip(bm)

    def test_solid_fill_saves_bytes(self):
        pg = P.parse('{white}The quick brown fox jumps over it\n' * 3)
        bm = render.render(pg, 1.5)
        packed = sixel.encode(bm)
        plain = sixel.encode(bm, solid_fill_off=True)
        self.assertLess(len(packed), len(plain))
        # and both describe the same picture
        self.assertEqual(decode(packed)[2], decode(plain)[2])

    def test_partial_last_band_is_not_overpainted(self):
        # 7 rows is one full band plus one of six: the solid fill must
        # not paint the five rows that are past the bottom
        bm = render.Bitmap(8, 7)
        for i in range(len(bm.pix)):
            bm.pix[i] = i % 3
        w, h, pixels, _ = decode(sixel.encode(bm))
        self.assertEqual(h, 7)
        self._roundtrip(bm)

    def test_rle(self):
        self.assertEqual(sixel._rle(bytearray([1, 1, 1, 1, 2])), '!4@A')
        self.assertEqual(sixel._rle(bytearray([1, 1, 2])), '@@A')
        self.assertEqual(sixel._rle(bytearray([0, 0, 0])), '')

    def test_raster_fit(self):
        pg = P.Page()
        ok, _ = sixel.fits(render.render(pg, 2), 'vt340')
        self.assertTrue(ok)
        ok, why = sixel.fits(render.render(pg, 3), 'vt340')
        self.assertFalse(ok)
        self.assertIn('VT340', why)

    def test_terminal_limits_registers(self):
        bm = render.Bitmap(6, 6, [(255, 0, 0)] * 20)
        for i in range(len(bm.pix)):
            bm.pix[i] = i % 20
        data = sixel.sequence(bm, terminal='vt340')
        used = set(int(n) for n in __import__('re').findall(r'#(\d+)', data))
        self.assertTrue(max(used) < 16)


class ColourRegisterTest(unittest.TestCase):
    """Writing past a terminal's register count corrupts the picture, so
    the limit is never optimistic."""

    def _args(self, **kw):
        from teletext import cli
        args = cli.build_parser().parse_args(['render', 'x'])
        for k, v in kw.items():
            setattr(args, k, v)
        return args

    def test_depth_names(self):
        from teletext import cli
        self.assertIsNone(cli._depth_limit(self._args(depth='auto')))
        self.assertEqual(cli._colour_limit(self._args(depth='low')), 16)
        self.assertEqual(cli._colour_limit(self._args(depth='medium')), 64)
        self.assertEqual(cli._colour_limit(self._args(depth='high')), 256)
        self.assertEqual(cli._colour_limit(self._args(depth='24')), 24)
        with self.assertRaises(ValueError):
            cli._depth_limit(self._args(depth='deep'))

    def test_depth_sets_the_photo_budget(self):
        from teletext import cli
        self.assertEqual(cli._photo_colours(self._args(depth='low')), 8)
        self.assertEqual(cli._photo_colours(self._args(depth='medium')), 56)
        self.assertEqual(cli._photo_colours(self._args(depth='high')), 64)

    def test_explicit_registers_beat_depth(self):
        from teletext import cli
        args = self._args(depth='high', colour_registers=16)
        self.assertEqual(cli._colour_limit(args), 16)

    def test_depth_caps_what_is_emitted(self):
        from teletext import cli
        import re as _re
        bm = render.Bitmap(40, 12,
                           [(i * 3 % 256, 255 - i * 3 % 256, 128)
                            for i in range(80)])
        for i in range(len(bm.pix)):
            bm.pix[i] = i % 80
        for depth, limit in (('low', 16), ('medium', 64), ('24', 24)):
            out = []
            cli._emit(bm, self._args(depth=depth, terminal='xterm'),
                      out.append)
            used = set(int(n) for n in _re.findall(r'#(\d+)', ''.join(out)))
            self.assertTrue(max(used) < limit,
                            '--depth %s emitted register %d'
                            % (depth, max(used)))

    def test_limit_precedence(self):
        from teletext import cli
        self.assertEqual(cli._colour_limit(self._args(terminal='vt340')), 16)
        self.assertEqual(cli._colour_limit(self._args(terminal='xterm')), 256)
        self.assertEqual(
            cli._colour_limit(self._args(terminal='xterm',
                                         _probed_registers=16)), 16)
        self.assertEqual(
            cli._colour_limit(self._args(terminal='xterm', colour_registers=4,
                                         _probed_registers=16)), 4)

    def test_nothing_is_emitted_past_the_limit(self):
        from teletext import cli
        bm = render.Bitmap(40, 12, [(i * 4, 255 - i * 4, 128) for i in range(64)])
        for i in range(len(bm.pix)):
            bm.pix[i] = i % 64
        for limit in (4, 16, 64):
            out = []
            args = self._args(terminal='xterm', colour_registers=limit)
            cli._emit(bm, args, out.append)
            used = set(int(n) for n in
                       __import__('re').findall(r'#(\d+)', ''.join(out)))
            self.assertTrue(max(used) < limit,
                            'register %d used with a limit of %d'
                            % (max(used), limit))

    def test_photo_keeps_within_the_spare_registers(self):
        from teletext import cli
        pg = P.Page()
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'p.png')
            photo = imageconv.Image(40, 30)
            for i in range(len(photo.pix)):
                photo.pix[i] = (i * 7) % 256
            imageconv.write_png(imageconv.quantize(photo, 200), src)
            pg.meta['image'] = src
            pg.meta['imagebox'] = '10,1,8,38'
            for limit in (16, 32):
                args = self._args(terminal='xterm', colour_registers=limit)
                bm = cli._render_page(pg, args)
                self.assertLessEqual(len(bm.palette), limit)


class FitTest(unittest.TestCase):
    """A page goes out as a single sixel image, so the whole thing has to
    fit the window or the top scrolls away."""

    def _args(self, **kw):
        from teletext import cli
        args = cli.build_parser().parse_args(['render', 'x'])
        for k, v in kw.items():
            setattr(args, k, v)
        return args

    def _rows_needed(self, args, cell_h):
        from teletext import cli
        pg = P.parse('{red}Hello\n')
        out = []
        cli._emit_page(pg, args, out.append)
        px = int(re.search(r'"\d+;\d+;\d+;(\d+)', ''.join(out)).group(1))
        return -(-px // cell_h)

    def test_the_page_fits_the_window_it_was_fitted_to(self):
        import shutil as _shutil
        from teletext import cli
        real = _shutil.get_terminal_size
        try:
            for cell_h, rows in ((20, 24), (14, 34), (16, 30), (20, 50),
                                 (20, 20), (12, 22)):
                _shutil.get_terminal_size = (
                    lambda r: (lambda fallback=(80, 24):
                               os.terminal_size((80, r))))(rows)
                args = self._args()
                args._cell_px = (10, cell_h)
                args.scale = cli._fit_scale(args)
                used = self._rows_needed(args, cell_h)
                self.assertLessEqual(
                    used, rows,
                    'scale %s needs %d rows in a %d-row window (cell %dpx)'
                    % (args.scale, used, rows, cell_h))
        finally:
            _shutil.get_terminal_size = real

    def test_a_window_too_small_for_any_scale_gets_the_smallest(self):
        import shutil as _shutil
        from teletext import cli
        real = _shutil.get_terminal_size
        try:
            _shutil.get_terminal_size = lambda fallback=(80, 24): \
                os.terminal_size((80, 6))
            args = self._args()
            args._cell_px = (10, 20)
            self.assertEqual(cli._fit_scale(args), min(cli.SCALE_LADDER))
        finally:
            _shutil.get_terminal_size = real

    def test_fit_scale_shrinks_for_a_small_cell(self):
        import shutil as _shutil
        from teletext import cli
        real = _shutil.get_terminal_size
        try:
            _shutil.get_terminal_size = lambda fallback=(80, 24): \
                os.terminal_size((80, 24))
            roomy = self._args()
            roomy._cell_px = (10, 20)          # a VT340-sized cell
            cramped = self._args()
            cramped._cell_px = (7, 12)         # a small font, same window
            self.assertGreater(cli._fit_scale(roomy), cli._fit_scale(cramped))
        finally:
            _shutil.get_terminal_size = real

    def test_fit_never_goes_above_the_default(self):
        import shutil as _shutil
        from teletext import cli
        real = _shutil.get_terminal_size
        try:
            _shutil.get_terminal_size = lambda fallback=(80, 24): \
                os.terminal_size((200, 200))   # all the room in the world
            args = self._args()
            args._cell_px = (10, 20)
            self.assertLessEqual(cli._fit_scale(args), cli.DEFAULT_SCALE)
        finally:
            _shutil.get_terminal_size = real

    def test_fractional_scale(self):
        pg = P.Page()
        bm = render.render(pg, 1.5)
        self.assertEqual((bm.width, bm.height), (360, 350))   # 9x14 cells
        self.assertEqual(len(bm.pix), 360 * 350)

    def test_fractional_scale_keeps_the_picture(self):
        pg = P.parse('{gwhite}{7F}{7F}{7F}\n')
        whole = render.render(pg, 2)
        part = render.render(pg, 1.5)
        self.assertTrue(any(part.pix))
        self.assertLess(sum(part.pix), sum(whole.pix))


class ImageTest(unittest.TestCase):
    def _gradient(self, w=32, h=24):
        img = imageconv.Image(w, h)
        for y in range(h):
            for x in range(w):
                o = (y * w + x) * 3
                img.pix[o] = x * 255 // w
                img.pix[o + 1] = y * 255 // h
                img.pix[o + 2] = 64
        return img

    def test_png_round_trip(self):
        bm = render.render(P.parse('{red}Hi\n'), 1)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'x.png')
            imageconv.write_png(bm, path)
            img = imageconv.load(path)
        self.assertEqual((img.width, img.height), (bm.width, bm.height))
        self.assertEqual(img.get(0, 0), render.PALETTE[bm.pix[0]])

    def test_resize_keeps_aspect(self):
        img = self._gradient(40, 10)
        out = img.resize(80, 75)
        self.assertEqual((out.width, out.height), (80, 75))

    def test_mono_page_uses_graphics_colour(self):
        pg = imageconv.to_page(self._gradient(), rows=6, mode='mono',
                               colour='cyan')
        self.assertEqual(pg.rows[0][0], P.GRAPHICS_CYAN)
        self.assertTrue(any(c > 0x20 for c in pg.rows[0][1:]))

    def test_colour_page_emits_graphics_codes(self):
        pg = imageconv.to_page(self._gradient(), rows=6, mode='colour')
        self.assertTrue(any(0x10 <= c <= 0x17 for c in pg.rows[0]))

    def test_rows_follow_the_aspect_ratio(self):
        # 38 cells is 76 mosaic pixels wide; 16:9 wants 43 down, so 14 rows
        wide = self._gradient(320, 180)
        self.assertEqual(imageconv.rows_for(wide, 38, 20), 14)
        self.assertEqual(imageconv.rows_for(wide, 38, 9), 9)   # capped
        tall = self._gradient(100, 300)
        self.assertEqual(imageconv.rows_for(tall, 38, 12), 12)

    def test_equalise_lifts_a_dark_picture(self):
        dark = imageconv.Image(20, 20)
        for i in range(len(dark.pix)):
            dark.pix[i] = i % 40                 # everything in the shadows
        out = imageconv.equalise(dark)
        self.assertGreater(sum(out.pix) / len(out.pix),
                           sum(dark.pix) / len(dark.pix))

    def test_hold_mosaics_cover_the_colour_changes(self):
        pg = imageconv.to_page(self._gradient(), rows=4, mode='colour')
        self.assertEqual(pg.rows[0][1], P.HOLD_MOSAICS)
        cells = render.row_cells(pg.rows[0])
        # no cell in the picture falls back to a blank attribute space
        self.assertTrue(all(c.gfx for c in cells[2:]))

    def test_dithering_uses_more_than_one_ink(self):
        img = imageconv.Image(80, 12)
        for i in range(80 * 12):                 # smooth grey ramp
            v = (i % 80) * 3
            img.pix[i * 3:i * 3 + 3] = bytes((v, v, v))
        pg = imageconv.to_page(img, rows=4, mode='colour')
        patterns = set(pg.rows[0][2:])
        self.assertGreater(len(patterns), 3)     # a ramp, not a hard edge

    def test_quantise_respects_the_colour_budget(self):
        bm = imageconv.quantize(self._gradient(40, 30), 8)
        self.assertLessEqual(len(bm.palette), 8)
        self.assertLessEqual(max(bm.pix), 7)

    def test_quantise_and_composite(self):
        bm = render.render(P.Page(), 1)
        imageconv.composite(bm, self._gradient(), (0, 0, 60, 60), ncolours=8)
        self.assertEqual(len(bm.palette), 16)
        self.assertTrue(max(bm.pix) >= 8)


class ArticleTest(unittest.TestCase):
    PAGE = b'''<html><body>
    <header><p>Menu and sign in</p></header>
    <script>var notArticle = 'never the body text';</script>
    <nav><p>Home News Sport</p></nav>
    <main>
    <p>The first paragraph of the actual story, which is long enough
       to count as real article text and mentions Ben &amp; Jerry.</p>
    <h2>A subhead</h2>
    <p>The second paragraph says rather more than the first one did,
       filling the page out nicely with plenty of its own words.</p>
    <figure><figcaption>A picture caption</figcaption></figure>
    <p>The third paragraph adds more story text so the total is well
       past the minimum that counts as an extraction.</p>
    </main>
    <footer><p>Copyright somebody</p></footer>
    </body></html>'''

    def test_extracts_the_story_not_the_chrome(self):
        paras = article.extract(self.PAGE)
        text = ' '.join(paras)
        self.assertIn('Ben & Jerry', text)
        self.assertIn('A subhead', text)
        for junk in ('Menu and sign in', 'notArticle', 'Home News Sport',
                     'A picture caption', 'Copyright somebody'):
            self.assertNotIn(junk, text)

    def test_root_paragraphs_are_preferred(self):
        # both paragraphs sit inside <main>, so nothing outside is kept
        paras = article.extract(self.PAGE)
        self.assertEqual(len(paras), 4)
        self.assertTrue(paras[0].startswith('The first paragraph'))

    def test_too_little_text_is_a_failure(self):
        self.assertEqual(article.extract(b'<p>Hi.</p>'), [])
        self.assertEqual(article.extract(b'<div>no blocks</div>'), [])

    def test_length_is_capped(self):
        page = b'<p>' + b'word ' * 400 + b'</p><p>and the end</p>'
        paras = article.extract(page, max_chars=500)
        self.assertLess(sum(len(p) + 1 for p in paras), 600)
        self.assertNotIn('and the end', ' '.join(paras))


class FeedTest(unittest.TestCase):
    SAMPLE = b'''<?xml version="1.0"?>
    <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
    <channel><title>BBC News</title>
    <item><title>Cat &amp; dog</title>
    <description>&lt;p&gt;It happened.&lt;/p&gt;</description>
    <link>http://example.invalid/1</link>
    <media:thumbnail url="http://example.invalid/small.jpg" width="240"/>
    <media:thumbnail url="http://example.invalid/big.jpg" width="976"/>
    </item></channel></rss>'''

    def test_parse(self):
        items = rss.parse(self.SAMPLE)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, 'Cat & dog')
        self.assertEqual(items[0].summary, 'It happened.')
        self.assertEqual(items[0].image, 'http://example.invalid/big.jpg')
        self.assertEqual(rss.feed_title(self.SAMPLE), 'BBC News')

    RDF_SAMPLE = b"""<?xml version="1.0" encoding="ISO-8859-1"?>
    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
     xmlns="http://purl.org/rss/1.0/"
     xmlns:dc="http://purl.org/dc/elements/1.1/">
    <channel rdf:about="http://example.invalid/">
    <title>Slashdot</title></channel>
    <item rdf:about="http://example.invalid/story/1">
    <title>Cops Searched Thousands of Cameras</title>
    <link>http://example.invalid/story/1</link>
    <description>404 Media reports: something happened.</description>
    <dc:date>2026-09-15T09:00:00+00:00</dc:date>
    </item></rdf:RDF>"""

    def test_rss_one_point_oh(self):
        """Slashdot is RDF: every element is namespaced, so a parser
        looking for a bare <item> finds nothing at all."""
        items = rss.parse(self.RDF_SAMPLE)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, 'Cops Searched Thousands of Cameras')
        self.assertEqual(items[0].summary, '404 Media reports: something '
                                           'happened.')
        self.assertEqual(items[0].link, 'http://example.invalid/story/1')
        self.assertEqual(items[0].published, '2026-09-15T09:00:00+00:00')
        self.assertEqual(rss.feed_title(self.RDF_SAMPLE), 'Slashdot')

    def test_all_three_formats_reach_the_same_item(self):
        for data in (self.SAMPLE, self.RDF_SAMPLE):
            items = rss.parse(data)
            self.assertTrue(items)
            self.assertTrue(items[0].title)
            self.assertTrue(items[0].link.startswith('http'))

    def test_slashdot_is_a_known_feed(self):
        title, url, base = sources.resolve('slashdot')
        self.assertEqual(base, 410)
        self.assertIn('slashdot', url)

    def test_bad_xml_is_a_clean_error(self):
        with self.assertRaises(ValueError):
            rss.parse(b'')
        with self.assertRaises(ValueError):
            rss.parse(b'<rss><channel>')

    def test_escape_keeps_pages_renderable(self):
        text = builder._escape('Smart ‘quotes’ — and €100')
        self.assertNotIn('‘', text)
        for ch in text:
            self.assertTrue(ord(ch) < 0x80 or ch in '£½¼¾÷')

    def test_fastext_bar_colours_and_order(self):
        """Red, green, yellow, cyan - the order every teletext service
        used, so the keys mean what a viewer expects."""
        pg = P.Page()
        P.fastext_bar(pg, [('PREV', 301), ('NEXT', 303), ('INDEX', 300),
                           ('MAIN', 100)])
        codes = [c for c in pg.rows[P.ROWS - 1] if c < 0x20]
        self.assertEqual(codes, [P.ALPHA_RED, P.ALPHA_GREEN, P.ALPHA_YELLOW,
                                 P.ALPHA_CYAN])
        text = pg.to_text().splitlines()[P.ROWS - 1]
        for word in ('PREV 301', 'NEXT 303', 'INDEX 300', 'MAIN 100'):
            self.assertIn(word, text)
        self.assertLessEqual(len(text), P.COLS)

    def test_fastext_bar_fits_whatever_it_is_given(self):
        for count in (1, 2, 3, 4):
            pg = P.Page()
            P.fastext_bar(pg, [('LABEL%d' % i, 100 + i) for i in range(count)])
            self.assertLessEqual(len(pg.to_text().splitlines()[P.ROWS - 1]),
                                 P.COLS)

    def test_every_key_names_a_page(self):
        """A key that is only a word is no use when you navigate by
        typing numbers."""
        item = rss.Item(title='Story', summary='Body.')
        pg = builder.build_story(item, 302, 'BBC SPORT', 100, prev=301,
                                 nxt=303, base=300, image_mode='none')
        text = pg.to_text().splitlines()[24]
        for want in ('PREV 301', 'NEXT 303', 'INDEX 300', 'MAIN 100'):
            self.assertIn(want, text)

    def test_front_page_keys_jump_to_the_services(self):
        pg = builder.build_front([('BBC NEWS', 101, 6), ('BBC SPORT', 300, 6),
                                  ('UK WEATHER', 400, 8)])
        text = pg.to_text().splitlines()[24]
        for base in ('101', '300', '400'):
            self.assertIn(base, text)

    def test_front_page_carries_the_hecnet_logo(self):
        pg = builder.build_front([('BBC NEWS', 101, 6)])
        self.assertNotIn('CEEFAX 100', pg.to_text())
        logo_rows = pg.rows[2:5]
        self.assertTrue(any(c == P.GRAPHICS_CYAN for row in logo_rows
                            for c in row))
        self.assertTrue(any(font.is_mosaic(c, True) and c != 0x20
                            for row in logo_rows for c in row))

    def test_logo_art_is_drawn_from_the_font(self):
        art = builder.logo_art('HECNET')
        self.assertEqual(len(art), font.CELL_H)          # nine pixel rows
        self.assertEqual(len(art[0]), 6 * font.CELL_W)   # six characters
        self.assertTrue(any('#' in line for line in art))

    def test_header_has_no_clock_by_default(self):
        """A page is a minute old by the time it has painted at 9600
        baud, and every page in a carousel would show a different
        minute; the date is what is worth knowing."""
        pg = P.Page()
        builder.header(pg, 102, 'BBC NEWS')
        text = pg.to_text().splitlines()[0]
        self.assertNotRegex(text, r'\d\d:\d\d')
        self.assertRegex(text, r'\d+ \w\w\w')          # the date stays

    def test_clock_can_be_put_back(self):
        pg = P.Page()
        builder.header(pg, 102, 'BBC NEWS', clock=True)
        self.assertRegex(pg.to_text().splitlines()[0], r'\d\d:\d\d')

    def test_dropping_the_clock_gives_the_service_name_room(self):
        long_name = 'BBC ENTERTAINMENT AND ARTS'
        with_clock, without = P.Page(), P.Page()
        builder.header(with_clock, 181, long_name, clock=True)
        builder.header(without, 181, long_name, clock=False)
        self.assertGreater(len(without.to_text().splitlines()[0].split('  ')[1]),
                           len(with_clock.to_text().splitlines()[0].split('  ')[1]))

    def test_front_page_nav_has_no_clock(self):
        pg = builder.build_front([('BBC NEWS', 101, 6)])
        self.assertNotRegex(pg.to_text().splitlines()[24], r'\d\d:\d\d')

    def test_header_fits_40_columns(self):
        pg = P.Page()
        builder.header(pg, 199, 'BBC ENTERTAINMENT AND ARTS')
        self.assertEqual(len(pg.rows[0]), P.COLS)
        self.assertEqual(pg.rows[0][0], P.ALPHA_CYAN)

    def test_service_pages(self):
        items = rss.parse(self.SAMPLE)
        pages = builder.build_service(items, 'BBC NEWS', 101, limit=4,
                                      image_mode='none')
        self.assertEqual([n for n, _ in pages], [101, 102])
        index = pages[0][1]
        self.assertIn('102', index.to_text())
        story = pages[1][1]
        self.assertIn('CAT & DOG', story.to_text())
        self.assertEqual(story.meta['link'], 'http://example.invalid/1')

    def test_story_page_uses_article_text_not_the_teaser(self):
        item = rss.Item(title='Big headline', summary='One teaser sentence.')
        paras = ['Paragraph %d carries quite a lot of words.' % i
                 for i in range(40)]
        pg = builder.build_story(item, 102, 'BBC NEWS', 100,
                                 image_mode='none', article=paras)
        text = pg.to_text()
        self.assertIn('Paragraph 0', text)
        self.assertNotIn('One teaser sentence', text)

    def test_story_page_keeps_two_paragraphs(self):
        """A story page is a summary: the opening paragraphs are the
        news, and the rest would only push the picture off the page."""
        item = rss.Item(title='Big headline', summary='Teaser.')
        paras = ['Paragraph %d carries quite a lot of words.' % i
                 for i in range(40)]
        pg = builder.build_story(item, 102, 'BBC NEWS', 100,
                                 image_mode='none', article=paras)
        text = pg.to_text()
        self.assertIn('Paragraph 0', text)
        self.assertIn('Paragraph 1', text)
        self.assertNotIn('Paragraph 2', text)

    def test_all_paragraphs_fill_the_page_when_asked(self):
        item = rss.Item(title='Big headline', summary='Teaser.')
        paras = ['Paragraph %d carries quite a lot of words.' % i
                 for i in range(40)]
        pg = builder.build_story(item, 102, 'BBC NEWS', 100,
                                 image_mode='none', article=paras,
                                 max_paragraphs=0)
        lines = pg.to_text().splitlines()
        self.assertTrue(lines[5].startswith('Paragraph 0'))
        for line in lines[5:23]:
            self.assertTrue(line.strip(), 'empty body row')
        self.assertTrue(lines[22].endswith('...'))   # the cut is marked

    def test_story_body_sits_under_the_headline(self):
        item = rss.Item(title='Big headline', summary='One teaser sentence.')
        paras = ['Paragraph %d carries quite a lot of words.' % i
                 for i in range(40)]
        pg = builder.build_story(item, 102, 'BBC NEWS', 100,
                                 image_mode='none', article=paras)
        lines = pg.to_text().splitlines()
        self.assertTrue(lines[5].startswith('Paragraph 0'))
        self.assertTrue(lines[2].strip().startswith('BIG HEADLINE'))

    def test_every_generated_row_fits(self):
        items = rss.parse(self.SAMPLE) * 6
        for _, pg in builder.build_service(items, 'BBC NEWS', 101,
                                           image_mode='none'):
            for row in pg.rows:
                self.assertEqual(len(row), P.COLS)


if __name__ == '__main__':
    unittest.main()


class WeatherTest(unittest.TestCase):
    """The degree signs matter: the feed is UTF-8 and the temperatures
    sit either side of them."""

    SAMPLE = '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>BBC Weather - Forecast for London, GB</title>\n<item><title>Today: Sunny Intervals, Minimum Temperature: 12°C (53°F) Maximum Temperature: 23°C (74°F)</title>\n<description>Maximum Temperature: 23°C (74°F), Minimum Temperature: 12°C (53°F), Wind Direction: south-westerly, Wind Speed: 11mph, Humidity: 47%</description></item>\n<item><title>Wednesday: Light Rain, Minimum Temperature: -2°C (28°F) Maximum Temperature: 4°C (39°F)</title>\n<description>Maximum Temperature: 4°C (39°F), Minimum Temperature: -2°C (28°F), Wind Direction: northerly, Wind Speed: 20mph, Humidity: 80%</description></item>\n</channel></rss>'.encode('utf-8')

    def test_parse(self):
        casts = weather.parse(self.SAMPLE)
        self.assertEqual(len(casts), 2)
        self.assertEqual(casts[0].day, 'Today')
        self.assertEqual(casts[0].condition, 'Sunny Intervals')
        self.assertEqual((casts[0].high, casts[0].low), (23, 12))
        self.assertEqual(casts[0].detail['Wind Speed'], '11mph')

    def test_negative_temperatures(self):
        casts = weather.parse(self.SAMPLE)
        self.assertEqual((casts[1].high, casts[1].low), (4, -2))

    def test_conditions_pick_a_colour_and_symbol(self):
        casts = weather.parse(self.SAMPLE)
        self.assertEqual(casts[0].kind(), ('yellow', 'sun'))
        self.assertEqual(casts[1].kind(), ('cyan', 'rain'))
        for _word, _colour, symbol in weather._KINDS:
            self.assertIn(symbol, weather.SYMBOLS)

    def test_conditions_are_abbreviated_to_fit(self):
        casts = weather.parse(self.SAMPLE)
        self.assertEqual(casts[0].short(13), 'Sunny ints')
        for name, _ in weather.LOCATIONS:
            self.assertLessEqual(len(name), 12, '%s will be truncated' % name)

    def test_every_location_fits_the_summary_page(self):
        """Nineteen locations in the list and nineteen rows to put them
        in: one more and a place would fall off the bottom."""
        casts = weather.parse(self.SAMPLE)
        places = [(name, casts) for name, _ in weather.LOCATIONS]
        pg = weather.build_summary(places, 400, 400)
        text = pg.to_text()
        for name, _ in weather.LOCATIONS:
            self.assertIn(name, text, '%s did not fit the page' % name)

    def test_cambridge_is_listed(self):
        self.assertIn('Cambridge', [n for n, _ in weather.LOCATIONS])

    def test_compass(self):
        self.assertEqual(weather.compass('south-westerly'), 'SW')
        self.assertEqual(weather.compass('northerly'), 'N')
        self.assertEqual(weather.compass(None), '')

    def test_every_symbol_is_eight_by_six(self):
        for name, art in weather.SYMBOLS.items():
            self.assertEqual(len(art), 6, name)
            for line in art:
                self.assertEqual(len(line), 8, name)

    def test_overnight_readings_are_not_lost(self):
        """After dark the feed gives a minimum and no maximum; a page
        that only ever shows maxima is blank all evening, and the map
        loses every label."""
        # the real overnight feed carries no maximum in the title or the
        # description, so the fixture has to drop both
        night = self.SAMPLE.replace(
            'Maximum Temperature: 23\u00b0C (74\u00b0F), '.encode('utf-8'),
            b'').replace(
            ' Maximum Temperature: 23\u00b0C (74\u00b0F)'.encode('utf-8'),
            b'')
        casts = weather.parse(night)
        self.assertIsNone(casts[0].high)
        self.assertEqual(weather.reading(casts[0]), 12)
        pg = weather.build_summary([('London', casts)], 401, 400)
        text = pg.to_text()
        self.assertIn('12', text)
        self.assertNotIn('Max', text)        # the column is dropped
        self.assertIn('Min', text)

    def test_daytime_keeps_both_columns(self):
        casts = weather.parse(self.SAMPLE)
        pg = weather.build_summary([('London', casts)], 401, 400)
        text = pg.to_text()
        self.assertIn('Max', text)
        self.assertIn('23', text)

    def test_summary_page(self):
        casts = weather.parse(self.SAMPLE)
        places = [('London', casts), ('Southampton', casts)]
        pg = weather.build_summary(places, 400, 400)
        text = pg.to_text()
        self.assertIn('London', text)
        self.assertIn('Southampton', text)      # not truncated
        self.assertIn('Sunny ints', text)
        self.assertIn('23', text)
        for row in pg.rows:
            self.assertEqual(len(row), P.COLS)

    def test_place_page_has_a_symbol(self):
        casts = weather.parse(self.SAMPLE)
        pg = weather.build_place('London', casts, 402, 100, 400)
        text = pg.to_text()
        self.assertIn('LONDON', text)
        self.assertIn('Wind SW 11mph', text)
        # the symbol is mosaic graphics, so a graphics colour code appears
        self.assertTrue(any(0x10 <= c <= 0x17 for row in pg.rows for c in row))

    def test_service_skips_locations_that_fail(self):
        def fetch_feed(url):
            return self.SAMPLE if url.endswith('/1') else None

        pages = weather.build_service(fetch_feed, base=400,
                                      locations=[('London', 1),
                                                 ('Nowhere', 2)])
        self.assertTrue(pages)
        self.assertEqual(pages[0][0], 400)
        self.assertIn('London', pages[0][1].to_text())
        self.assertNotIn('Nowhere', pages[0][1].to_text())

    def test_service_with_nothing_available(self):
        self.assertEqual(weather.build_service(lambda url: None), [])

    def test_service_numbers_run_on_from_the_summaries(self):
        pages = weather.build_service(lambda url: self.SAMPLE, base=400,
                                      locations=weather.LOCATIONS[:3])
        numbers = [n for n, _ in pages]
        self.assertEqual(numbers[:3], [400, 401, 402])
        self.assertEqual(len(numbers), len(set(numbers)))


class MapTest(unittest.TestCase):
    """The map is only readable if the cities are where they belong."""

    def test_projection_puts_cities_in_the_right_places(self):
        proj = ukmap.Projection(200, 260)
        at = dict((name, proj(*pos)) for name, pos in ukmap.CITIES.items())
        self.assertGreater(at['London'][1], at['Edinburgh'][1])   # further down
        self.assertGreater(at['London'][0], at['Cardiff'][0])     # further right
        self.assertLess(at['Inverness'][1], at['Manchester'][1])
        self.assertLess(at['Belfast'][0], at['Newcastle'][0])
        self.assertGreater(at['Norwich'][0], at['Birmingham'][0])
        for name, (x, y) in at.items():
            self.assertTrue(0 <= x < 200 and 0 <= y < 260,
                            '%s fell off the map at %d,%d' % (name, x, y))

    def test_longitude_is_squeezed(self):
        """Without the cosine the country comes out far too wide."""
        proj = ukmap.Projection(200, 260)
        self.assertLess(proj.kx, 0.7)

    def test_draw_gives_sea_and_land(self):
        img = ukmap.draw(180, 270)
        self.assertEqual((img.width, img.height), (180, 270))
        self.assertEqual(img.get(2, 2), ukmap.SEA)          # corner is sea
        proj = ukmap.Projection(180, 270)
        x, y = proj(52.5, -1.5)                             # the Midlands
        self.assertIn(img.get(x, y), (ukmap.LAND, ukmap.COAST))

    def test_a_mark_draws_a_label(self):
        plain = ukmap.draw(180, 270)
        marked = ukmap.draw(180, 270, [('London', '23', (255, 255, 0))])
        self.assertNotEqual(plain.pix, marked.pix)

    def test_crowded_labels_are_dropped_not_overprinted(self):
        """Two labels wanting the same space: the second is dropped, so
        nothing is printed over anything else."""
        twice = ukmap.draw(180, 270, [('London', '23', (255, 255, 0)),
                                      ('London', '99', (255, 0, 0))])
        once = ukmap.draw(180, 270, [('London', '23', (255, 255, 0))])
        self.assertEqual(twice.pix, once.pix)

    def test_a_crowded_map_drops_some_labels(self):
        marks = [(n, '23', (255, 255, 0)) for n in ukmap.CITIES]
        crowded = ukmap.draw(120, 180, marks)      # small: many collide
        roomy = ukmap.draw(300, 420, marks)
        def labelled(img):
            return sum(1 for i in range(0, len(img.pix), 3)
                       if tuple(img.pix[i:i + 3]) == (255, 255, 0))
        self.assertGreater(labelled(roomy), labelled(crowded))

    def test_every_weather_location_is_on_the_map(self):
        for name, _ in weather.LOCATIONS:
            self.assertIn(name, ukmap.CITIES, '%s has no position' % name)

    def test_map_page_writes_an_image_and_points_at_it(self):
        casts = WeatherTest().SAMPLE
        casts = weather.parse(casts)
        places = [(n, casts) for n, _ in weather.LOCATIONS[:4]]
        with tempfile.TemporaryDirectory() as d:
            pg = weather.build_map_page(places, 400, image_dir=d)
            self.assertIsNotNone(pg)
            # stored relative to the page, so the directory can be moved
            self.assertEqual(os.path.dirname(pg.meta['image']), '')
            path = os.path.join(d, pg.meta['image'])
            self.assertTrue(os.path.exists(path))
            self.assertEqual(pg.meta['imagebox'], '%d,%d,%d,%d'
                             % (weather.MAP_TOP, weather.MAP_LEFT,
                                weather.MAP_ROWS, weather.MAP_COLS))
            img = imageconv.load(path)
            self.assertEqual(img.width,
                             weather.MAP_COLS * font.CELL_W * 3 // 2)
            # the list down the right-hand side names the places
            self.assertIn('London', pg.to_text())

    def test_no_map_without_somewhere_to_put_it(self):
        casts = weather.parse(WeatherTest.SAMPLE)
        self.assertIsNone(weather.build_map_page([('London', casts)], 400))

    def test_service_starts_with_the_map(self):
        casts = WeatherTest.SAMPLE
        with tempfile.TemporaryDirectory() as d:
            pages = weather.build_service(
                lambda url: casts, base=400, image_dir=d,
                locations=weather.LOCATIONS[:2])
            numbers = [n for n, _ in pages]
            self.assertEqual(numbers[:3], [400, 401, 402])
            self.assertEqual(pages[0][1].meta.get('role'), 'weather')
            self.assertIn('image', pages[0][1].meta)
            self.assertNotIn('image', pages[1][1].meta)   # the table


class EditorTest(unittest.TestCase):
    """The key handling works without a terminal attached."""

    def setUp(self):
        from teletext import editor
        self.editor = editor
        self.state = {'page': P.Page(), 'path': 'x.ttx', 'row': 0, 'col': 0,
                      'pixel': False, 'dirty': False, 'msg': ''}

    def test_typing_advances(self):
        self.editor._handle(None, self.state, ord('A'))
        self.assertEqual(self.state['page'].rows[0][0], 0x41)
        self.assertEqual(self.state['col'], 1)
        self.assertTrue(self.state['dirty'])

    def test_pixel_mode_toggles_blocks(self):
        self.state['pixel'] = True
        for key in 'qwaszx':
            self.editor._handle(None, self.state, ord(key))
        self.assertEqual(self.state['page'].rows[0][0], P.mosaic_code(0x3F))
        self.editor._handle(None, self.state, ord('q'))
        self.assertEqual(self.state['page'].rows[0][0], P.mosaic_code(0x3E))

    def test_row_operations(self):
        pg = self.state['page']
        pg.write(0, 0, 'AAA')
        self.editor._handle(None, self.state, 4)         # ^D duplicate
        self.assertEqual(pg.rows[0], pg.rows[1])
        self.assertEqual(len(pg.rows), P.ROWS)
        self.editor._handle(None, self.state, 25)        # ^Y delete
        self.assertEqual(len(pg.rows), P.ROWS)

    def test_every_escape_key_is_a_real_control_code(self):
        for key, code in self.editor.ESC_KEYS.items():
            self.assertTrue(code < 0x20, '%s -> %02X' % (key, code))


class PublishTest(unittest.TestCase):
    """Pages published for a PDP-11 to fetch and TYPE."""

    def setUp(self):
        from teletext import cli
        self.cli = cli
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        stack = contextlib.ExitStack()
        self.out = stack.enter_context(
            contextlib.redirect_stdout(io.StringIO()))
        self.err = stack.enter_context(
            contextlib.redirect_stderr(io.StringIO()))
        self.addCleanup(stack.close)

    def _pages(self, numbers):
        d = os.path.join(self.tmp.name, 'pages')
        os.makedirs(d)
        for n in numbers:
            with open(os.path.join(d, '%s.ttx' % n), 'w') as fh:
                fh.write('!page %s\n!title Page %s\n{red}Page %s\n'
                         % (n, n, n))
        return d

    def _publish(self, numbers, *extra):
        out = os.path.join(self.tmp.name, 'pub')
        rc = self.cli.main(['publish', self._pages(numbers), '--out', out,
                            '--scale', '1', '--record', '200'] + list(extra))
        self.assertEqual(rc, 0)
        return out, sorted(os.listdir(out))

    def test_one_dat_per_page_plus_not_found(self):
        out, files = self._publish(['100', '101', '302'])
        for name in ('P100.DAT', 'P101.DAT', 'P302.DAT', 'PNF.DAT'):
            self.assertIn(name, files)

    def test_records_fit_the_filesystem(self):
        out, files = self._publish(['100'])
        with open(os.path.join(out, 'P100.DAT'), encoding='latin-1') as fh:
            for line in fh:
                self.assertLessEqual(len(line.rstrip('\n')), 200)

    def test_wrapping_does_not_change_the_picture(self):
        """Breaks fall between whole sixel tokens, never inside a
        run-length count, so the page is byte-different but pixel-same."""
        pg = P.parse('{red}Hello {gcyan}{7F}{yellow}World\n{green}{double}BIG\n')
        bm = render.render(pg, 1.5)
        raw = sixel.encode(bm)
        for width in (80, 200, 480):
            wrapped = sixel.wrap(raw, width)
            self.assertLessEqual(max(len(l) for l in wrapped.split('\n')),
                                 width)
            self.assertEqual(decode(wrapped)[2], decode(raw)[2],
                             'wrapping at %d changed the picture' % width)

    def test_a_directory_page_is_generated(self):
        out, files = self._publish(['100', '101', '302'])
        self.assertIn('P199.DAT', files)          # the generated index

    def test_a_page_list_names_every_page_in_order(self):
        out, files = self._publish(['302', '100', '101'])
        self.assertIn('PIDX.DAT', files)
        with open(os.path.join(out, 'PIDX.DAT'), encoding='latin-1') as fh:
            lines = fh.read().splitlines()
        self.assertEqual([l.split()[0] for l in lines],
                         ['100', '101', '199', '302'])
        self.assertEqual(lines[0], '100 Page 100')

    def test_the_page_list_can_be_left_out(self):
        out, files = self._publish(['100'], '--no-page-list')
        self.assertNotIn('PIDX.DAT', files)

    def test_page_list_titles_are_plain_and_fit(self):
        text = self.cli.page_list([('1000', 'x'), ('99', 'Caf\xe9\x1b[1m'),
                                   ('99', 'dup')], record=8)
        self.assertEqual(text, '99 Caf[1\n1000 x\n')

    def test_the_directory_lists_every_page(self):
        entries = [('%d' % n, 'Title %d' % n) for n in range(100, 108)]
        pages = self.cli._index_pages(entries, 199, set())
        text = '\n'.join(pg.to_text() for _, pg in pages)
        for number, title in entries:
            self.assertIn(number, text)
            self.assertIn(title, text)

    def test_a_long_list_continues_onto_further_pages(self):
        entries = [('%d' % n, 'Title') for n in range(100, 140)]
        pages = self.cli._index_pages(entries, 199, set())
        self.assertGreater(len(pages), 1)
        numbers = [n for n, _ in pages]
        self.assertEqual(numbers, sorted(numbers))
        self.assertEqual(len(numbers), len(set(numbers)))
        # each page points at the next
        self.assertIn(str(numbers[1]), pages[0][1].to_text())

    def test_the_directory_does_not_take_a_used_number(self):
        entries = [('199', 'Taken'), ('200', 'Also taken')]
        pages = self.cli._index_pages(entries, 199, {'199', '200'})
        self.assertNotIn(pages[0][0], (199, 200))

    def test_no_index_when_asked(self):
        out, files = self._publish(['100'], '--no-index')
        self.assertNotIn('P199.DAT', files)


class CommandTest(unittest.TestCase):
    """Every subcommand is actually invoked here: the shared helpers read
    attributes off the parsed namespace, so a subparser that forgets an
    option only fails at run time."""

    def setUp(self):
        from teletext import cli
        self.cli = cli
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # these commands legitimately print pages and progress; keep the
        # test run readable
        stack = contextlib.ExitStack()
        self.out = stack.enter_context(
            contextlib.redirect_stdout(io.StringIO()))
        self.err = stack.enter_context(
            contextlib.redirect_stderr(io.StringIO()))
        self.addCleanup(stack.close)

    def _path(self, name):
        return os.path.join(self.tmp.name, name)

    def _page(self):
        path = self._path('p.ttx')
        with open(path, 'w') as fh:
            fh.write('{red}{double}HELLO\n{gcyan}{7F}{7F}\n')
        return path

    def test_render(self):
        out = self._path('o.six')
        self.assertEqual(self.cli.main(['render', self._page(), '-o', out]), 0)
        with open(out) as fh:
            self.assertTrue(fh.read().startswith('\x1bP'))

    def test_render_loop_options(self):
        out = self._path('o.six')
        self.assertEqual(self.cli.main(
            ['render', self._page(), '--loop', '--repeat', '2',
             '--delay', '0', '-o', out]), 0)

    def test_demo(self):
        out = self._path('demo.six')
        self.assertEqual(self.cli.main(['demo', '-o', out]), 0)
        self.assertTrue(os.path.getsize(out) > 1000)

    def test_demo_takes_the_same_loop_options_as_render(self):
        out = self._path('demo.six')
        self.assertEqual(self.cli.main(
            ['demo', '--loop', '--repeat', '2', '--delay', '0', '-o', out]), 0)

    def test_chars(self):
        out = self._path('chars.six')
        for extra in ([], ['--charset', 'ascii']):
            self.assertEqual(self.cli.main(['chars', '-o', out] + extra), 0)

    def test_png_output(self):
        out = self._path('o.png')
        self.assertEqual(self.cli.main(['render', self._page(), '--png', out]), 0)
        img = imageconv.load(out)
        self.assertEqual((img.width, img.height), (360, 350))   # 9x14 cells
        self.assertEqual(self.cli.main(
            ['render', self._page(), '--scale', '2', '--png', out]), 0)
        img = imageconv.load(out)
        self.assertEqual((img.width, img.height), (480, 450))

    def test_mono_and_terminal_options(self):
        out = self._path('o.six')
        self.assertEqual(self.cli.main(
            ['render', self._page(), '--scale', '1', '--mono', '--ink', 'green',
             '--terminal', 'vt240', '--transparent', '--clear', '-o', out]), 0)

    def test_new_then_edit_round_trip(self):
        path = self._path('new.ttx')
        self.assertEqual(self.cli.main(['new', path, '--number', '200']), 0)
        self.assertEqual(self.cli.main(['text', path]), 0)
        self.assertEqual(self.cli.main(['preview', path]), 0)

    def test_image_to_page_and_sixel(self):
        png = self._path('src.png')
        imageconv.write_png(render.render(P.parse('{yellow}XY\n'), 1), png)
        ttx = self._path('img.ttx')
        self.assertEqual(self.cli.main(['image', png, '-o', ttx]), 0)
        self.assertEqual(self.cli.main(
            ['image', png, '--as', 'sixel', '--width', '60',
             '-o', self._path('img.six')]), 0)

    def test_view_without_a_terminal_just_renders(self):
        # stdout is redirected in setUp, so this takes the non-interactive
        # path instead of blocking on a keypress
        self.assertEqual(self.cli.main(['view', self._page()]), 0)
        self.assertTrue(self.out.getvalue().startswith('\x1bP'))

    def test_a_directory_expands_to_its_pages(self):
        d = self._path('svc')
        os.makedirs(d)
        for n in (102, 101, 100):
            with open(os.path.join(d, '%d.ttx' % n), 'w') as fh:
                fh.write('{red}page %d\n' % n)
        files = self.cli._expand_files([d])
        self.assertEqual([os.path.basename(f) for f in files],
                         ['100.ttx', '101.ttx', '102.ttx'])
        self.assertEqual(self.cli.main(['view', d]), 0)
        self.assertEqual(self.out.getvalue().count('\x1bP'), 3)
        self.assertEqual(self.cli.main(['render', d, '-o', self._path('d.six')]), 0)

    def test_view_defaults_to_the_bundled_pages(self):
        self.assertEqual(self.cli.main(['view']), 0)
        self.assertGreaterEqual(self.out.getvalue().count('\x1bP'), 2)

    def test_feeds_reports_a_bad_feed_without_a_traceback(self):
        bad = self._path('bad.xml')
        with open(bad, 'w') as fh:
            fh.write('not xml at all')
        self.assertEqual(self.cli.main(
            ['feeds', 'build', 'news', '--from-file', bad,
             '--out', self._path('p2')]), 1)
        self.assertIn('not valid RSS or Atom', self.err.getvalue())

    def test_feeds_build_from_file(self):
        xml = self._path('feed.xml')
        with open(xml, 'wb') as fh:
            fh.write(FeedTest.SAMPLE)
        outdir = self._path('pages')
        self.assertEqual(self.cli.main(
            ['feeds', 'build', 'news', '--from-file', xml, '--out', outdir,
             '--images', 'none', '--front', '--no-full-text']), 0)
        self.assertTrue(os.path.exists(os.path.join(outdir, '102.ttx')))
        self.assertEqual(self.cli.main(
            ['render', os.path.join(outdir, '102.ttx'),
             '-o', self._path('n.six')]), 0)
