import time
import gc
import board
import neopixel
from digitalio import DigitalInOut, Direction, Pull
import usb_midi
import adafruit_midi
from adafruit_midi.note_on import NoteOn
from adafruit_midi.note_off import NoteOff
from adafruit_debouncer import Debouncer
import json

class Col:
    
    RED = (255, 0, 0)
    YELLOW = (255, 150, 0)
    GREEN = (0, 255, 0)
    CYAN = (0, 255, 255)
    BLUE = (0, 0, 255)
    MAGENTA = (255, 0, 255)
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    GREY = (10, 10, 10)
    VIOLET = (127,0,155)
    INDIGO = (75,0,130)
    ORANGE = (255,165,0)
       
    values=(RED, GREEN, BLUE, YELLOW, MAGENTA, CYAN, GREY, WHITE)
    
   
    @staticmethod
    def dim(col):
        return (col[0]/40, col[1]/40, col[2]/40)
    
class Button():
    def __init__(self, client, pin, pixel):
        self.client =  client
        tmp_pin = DigitalInOut(pin)
        tmp_pin.pull = Pull.UP
        self.debounce = Debouncer(tmp_pin,interval=0.01)
        self.pixel = pixel
        
    def update(self):
        self.debounce.update()
        if self.debounce.fell:
            self.key_fell()

        if self.debounce.rose:
            self.key_rose()
            
class Note(Button):
    
    def __init__(self,client,pin,pixel,num):
        super(Note,self).__init__(client,pin,pixel)
        self.num = num
        self.last_note = -1
        self.last_chan = -1
        self.vol = 0
    
    def key_fell(self):
        self.client.note_down(self)

    def key_rose(self):
        self.client.note_up(self)
        
    def note_off(self):
        last_note = self.last_note
        if last_note != -1:
            chan = self.last_chan
            self.client.midi.send(NoteOff(last_note,0,channel=chan))
            self.last_note=-1
            
    def note_on(self,note_to_play, vol, chan):
        self.last_note=note_to_play
        self.vol = vol
        self.last_chan = chan
        self.client.midi.send(NoteOn(note_to_play, vol,channel=chan))
        
class Select(Button):
    
    def __init__(self,client,pin,pixel,col):
        super(Select,self).__init__(client,pin,pixel)
        self.col = col

    def key_fell(self):
        self.client.sel_down(self)

    def key_rose(self):
        self.client.sel_up(self)
        
class Setting():
    
    def __init__(self,name,cols,values, init,handler=None):
        self.name = name
        self.cols = cols
        self.values = values
        self.value = init
        self.init = init
        self.handler = handler
    
    def get_value(self):
        return self.values[self.value]
    
    def get_colour(self):
        return self.cols[self.value]
    
    def set_from_value(self,in_val):
        self.value=0
        for val in self.values:
            if val == in_val:
                return True
            self.value =  self.value+1
        
    def step(self):
        self.value = (self.value + 1) % len(self.values)
        if self.handler != None:
            self.handler(self)
            
    def reset(self):
        self.value = self.init
        
    def dumps(self):
        pass
        
    def loads(self,source):
        pass

class Step(Setting):
    def __init__(self,name,cols,values, init,handler=None):
        super(Step,self).__init__(name,cols,values,init,handler)
  
class Voice():
    def __init__(self,client,col,chan):
        self.client = client
        self.col = col
        self.dim = Col.dim(col)
        self.chan = chan
        self.init_chan = chan
            
    def show_settings(self):
        for note in self.client.notes:
            if note.num>=len(self.settings):
                col = Col.BLACK
            else:
                col = self.settings[note.num].get_colour()
            self.client.pixels[note.pixel]=col

    def reset(self):
        for setting in self.settings:
            setting.reset()
        self.chan = self.init_chan

    def option_down(self,note):
        if note.num<len(self.settings):
            self.settings[note.num].step()
    
    def dumps(self):
        pass
        
    def loads(self,source):
        pass
        
class Keyboard(Voice):

    scales = (
        ( 0, 2, 4, 5, 7, 9, 11, 12 ), #major
        ( 0, 2, 3, 5, 7, 8, 10, 12 ), #minor
        ( 0, 2, 3, 5, 7, 9, 10, 12 ), #dorian
        ( 0, 1, 3, 5, 7, 8, 10, 12 ), #phrygian
        ( 0, 2, 4, 6, 7, 9, 11, 12 ), #lydian
        ( 0, 2, 4, 5, 7, 9, 10, 12 ), #mixolydian
        ( 0, 1, 3, 5, 6, 8, 10, 12 )  #locrian
        )
    
    sequencer_run = (False, True)
    
    volumes = (30,80,120)
    octaves = (36,48,60,72,84)
    sharp_offsets = (0,1,-1)
    key_offsets = (0,2,4,5,7,-3,-1)
    
    midi = (0,1,2,3,4,5,6,7)
    
    set_run = 0
    set_vol = 1
    set_scale = 2
    set_oct = 3
    set_key=4
    set_sharpflat=5
    set_midi=6
    
    def run_changed(self,setting):
        if setting.get_value()==True:
            for item in self.client.sounds:
                if isinstance(item,Rhythm):
                    item.start_sequence = True
        else:
            for item in self.client.sounds:
                if isinstance(item,Rhythm):
                    item.stop_sequence = True
    
    def __init__(self,client,col,chan):
        super(Keyboard,self).__init__(client,col,chan)
        self.settings = (
            Setting("run",Col.values, Keyboard.sequencer_run,1,handler=self.run_changed),#0
            Setting("vol",Col.values, Keyboard.volumes,1),#1
            Setting("scale",Col.values, Keyboard.scales,0), #2
            Setting("Octave",Col.values, Keyboard.octaves,3),#3
            Setting("key",Col.values, Keyboard.key_offsets,0),  #4
            Setting("sharp",Col.values, Keyboard.sharp_offsets,0),  #5
            Setting("Midi",Col.values, Keyboard.midi,0)  #6
            )
        self.settings[Keyboard.set_midi].set_from_value(self.init_chan)
    
    def get_note(self, num):
        octave=self.settings[Keyboard.set_oct].get_value()
        scale=self.settings[Keyboard.set_scale].get_value()
        key_offset=self.settings[Keyboard.set_sharpflat].get_value()
        scale_offset=self.settings[Keyboard.set_key].get_value()
        start = octave + key_offset + scale_offset
        while num > 7:
            num = num - 8
            start = start + 12
        note = start+scale[num]
        return note
        
    def note_down(self,note):
        self.client.pixels[note.pixel]=Col.WHITE
        note_to_play = self.get_note(note.num)
        chan = self.settings[Keyboard.set_midi].get_value()
        vol=self.settings[Keyboard.set_vol].get_value()
        note.note_on(note_to_play, vol, chan)
    
    def note_up(self,note):
        note.note_off()
        self.client.pixels[note.pixel]=Col.GREY
        
    def draw_background(self):
        for select in self.client.selects:
            self.client.pixels[select.pixel]=Col.BLACK
        self.client.pixels[self.client.selects[0].pixel] = self.col
        for note in self.client.notes:
            self.client.pixels[note.pixel]=Col.GREY
            
    def reset(self):
        super(Keyboard,self).reset()
        for note in self.client.notes:
            note.note_off()
        self.settings[Keyboard.set_midi].set_from_value(self.init_chan)
            
    def update(self):
        pass

class Rhythm(Voice):
    
    sounds = (
        0,  # note off
        36, # kick drum
        40, # snare drum
        48, # mid tom
        59, # ride cymbal
        55, # splash cymbal
        39, # hand clap
        56  # cowbell
        )
    
    index = (0,1,2,3,4,5,6,7)
    
    rhythm_cols=(Col.BLACK, Col.RED, Col.GREEN, Col.BLUE, Col.YELLOW, Col.MAGENTA, Col.CYAN, Col.GREY, Col.WHITE)
    
    DRUM = 0
    NOTE = 1
    EUCLID = 2
    MULTI = 3
    
    run = (False, True)
    speed = (60,80,100,110,120,140,160,180)
    length = (2,3,4,5,6,7,8)
    factor = (1,2,3,4,5,6,7,8)
    volumes = (30,80,120)
    midi = (0,1,2,3,4,5,6,7)
    func = (0,1,2,3)
    loops = (1,2,3,4)

    set_run = 0
    set_vol = 1
    set_speed = 2
    set_length = 3
    set_factor = 4
    set_midi=5
    set_func=6
    set_loops=7
    
    def __init__(self,client,col,chan):
        super(Rhythm,self).__init__(client,col,chan)
        self.base = 45
        self.note_volume = 120
        self.start_sequence = False
        self.stop_sequence = False
        self.sequencing = False
        self.sequence_pos=0
        self.factor=0
        self.track = []
        for i in range(1,33):
            id="s"+str(i)
            step = Step(id,Rhythm.rhythm_cols, Rhythm.index,0)
            self.track.append(step)
        self.settings = (
            Setting("run",Col.values, Rhythm.run,1,handler=self.run_changed),       #0
            Setting("vol",Col.values, Rhythm.volumes,2),                            #1
            Setting("speed",Col.values, Rhythm.speed,4),   #2
            Setting("length",Col.values, Rhythm.length,6), #3
            Setting("factor",Col.values, Rhythm.factor,0), #4
            Setting("midi",Col.values, Rhythm.midi,0),  #5
            Setting("func",Col.values, Rhythm.func,0),   #6
            Setting("loops",Col.values, Rhythm.loops,0)   #7
            )
        self.settings[Rhythm.set_midi].set_from_value(self.chan)
        self.run_changed(self.settings[Rhythm.set_run])
    
    def run_changed(self,setting):
        if setting.get_value()==True:
            self.start_sequence = True
        else:
            self.stop_sequence = True
        
    def note_down(self,note):
        pos = self.sequence_pos
        no_of_loops=int(pos)//8
        if note.num<len(self.track):
            num = note.num + (no_of_loops * 8)
            self.track[num].step()
            self.client.pixels[note.pixel]=self.track[num].get_colour()
            
    def note_up(self,note):
        pass
    
    def draw_background(self):
        pos = self.sequence_pos
        no_of_loops=int(pos)//8
        i=0
        sel = self.client.selects
        while i<len(sel):
            pix=self.client.pixels
            pix_no = sel[i].pixel
            if i<=no_of_loops:
                pix[pix_no]=self.col
            else:
                pix[pix_no]=self.dim
            i = i + 1

        i = (no_of_loops*8)
        for note in self.client.notes:
            self.client.pixels[note.pixel]=self.track[i].get_colour()
            i = i + 1
        i = (self.sequence_pos % 8)
        pixel = self.client.notes[i].pixel
        self.client.pixels[pixel]=Col.WHITE

    def last_note_off(self):
        if self.need_redraw and not self.client.settings_active and self.client.target==self:
            self.draw_background()
        if self.last_note != -1:
            chan = self.settings[Rhythm.set_midi].get_value()
            self.client.midi.send(NoteOff(self.last_note,0),channel=chan)
            self.last_note = -1
        
    def reset_seq(self):
        self.sequence_pos=self.settings[Rhythm.set_length].get_value()-1
        self.time = self.client.time
        self.next_note = self.time
        self.last_note = -1
        self.need_redraw = False

    def reset(self):
        super(Rhythm,self).reset()
        self.last_note_off()
        for step in self.track:
            step.reset()
        self.settings[Rhythm.set_midi].set_from_value(self.init_chan)
        
    def update(self):
        
        if self.stop_sequence:
            self.last_note_off()
            self.sequencing = False
            self.stop_sequence = False
            return

        if self.start_sequence:
            self.start_sequence = False
            self.sequencing = True
            self.reset_seq()
            
        if self.client.reset_time:
            self.reset_seq()

        if self.sequencing:
            if self.client.time >= self.next_note:
                interval = 60 / self.settings[Rhythm.set_speed].get_value()
                self.next_note = self.next_note + interval
                self.factor = self.factor + 1
                factor_limit = self.settings[Rhythm.set_factor].get_value()
                if self.factor < factor_limit:
                    return
                self.factor=0    
                self.last_note_off()
                seq_length = (self.settings[Rhythm.set_loops].get_value()-1)*8
                seq_length = seq_length+self.settings[Rhythm.set_length].get_value() 
                self.sequence_pos = (self.sequence_pos + 1) % seq_length
                if self==self.client.target and not self.client.settings_active:
                    self.draw_background()
                    self.need_redraw=True
                else:
                    self.need_redraw=False
                index = self.track[self.sequence_pos].get_value()
                if index != 0:
                    vol=self.settings[Rhythm.set_vol].get_value()
                    func=self.settings[Rhythm.set_func].get_value()
                    if func==Rhythm.DRUM:
                        note=self.sounds[index]
                    elif func==Rhythm.NOTE:
                        keyboard = self.client.sounds[0]
                        note=keyboard.get_note(index-1)
                    elif func==Rhythm.EUCLID:
                        if self.client.euclid_played:
                            return
                        self.client.euclid_played = True
                        keyboard = self.client.sounds[0]
                        note_total=0
                        for item in self.client.sounds:
                            if isinstance(item,Rhythm):
                                item_func=item.settings[Rhythm.set_func].get_value()
                                if item_func == Rhythm.EUCLID:
                                    item_index = item.track[item.sequence_pos].get_value()
                                    scale = keyboard.settings[Keyboard.set_scale].get_value()
                                    note_to_add = scale[item_index]
                                    note_total = note_total + note_to_add
                        keyboard = self.client.sounds[0]
                        note=keyboard.get_note(note_total-1)
                    elif func==Rhythm.MULTI:
                        note=60
                    self.last_note = note
                    chan = self.settings[Rhythm.set_midi].get_value()
                    self.client.midi.send(NoteOn(note, vol),channel=chan)
        
class MidiBox():
    
    def note_down(self,note):
        self.no_of_notes_pressed = self.no_of_notes_pressed+1
        if self.settings_active:
            self.target.option_down(note)
            self.target.show_settings()
        else:
             self.target.note_down(note)
        self.pixels.show()

    def notes_off(self):
        for note in self.notes:
            note.note_off()
            
    def note_up(self,note):
        self.no_of_notes_pressed = self.no_of_notes_pressed-1
        if not self.settings_active:
            self.target.note_up(note)
            self.pixels.show()
        
    def sel_down(self, select):
        self.no_of_selects_pressed = self.no_of_selects_pressed+1
        if self.no_of_notes_pressed != 0:
            return
        if self.no_of_selects_pressed == 3:
            for sound in self.sounds:
                sound.reset()
        if self.settings_active:
            return
        if select.col != self.target.col:
            self.notes_off()
            self.pixels[self.select_pixel]=Col.BLACK
            self.select_voice(select.col)
        else:
            self.target.show_settings()
            self.settings_active=True
        self.pixels.show()
    
    def sel_up(self, select):
        self.no_of_selects_pressed = self.no_of_selects_pressed-1
        if self.settings_active:
            if select.col == self.target.col:
                self.settings_active=False
                self.target.draw_background()
                self.pixels.show()
                
    def set_note_col(self,col):
        for note in self.notes:
            self.pixels[note.pixel]=col
        self.pixels.show()
        
    def select_voice(self, col):
        for sound in self.sounds:
            if(sound.col == col):
                self.target = sound
                sound.draw_background()
                
    def __init__(self):
        self.notes = (
            Note(self,pin=board.GP6,pixel=11,num=0),
            Note(self,pin=board.GP5,pixel=10,num=1),
            Note(self,pin=board.GP4,pixel=9,num=2),
            Note(self,pin=board.GP3,pixel=8,num=3),
            Note(self,pin=board.GP2,pixel=7,num=4),
            Note(self,pin=board.GP1,pixel=6,num=5),
            Note(self,pin=board.GP12,pixel=5,num=6),
            Note(self,pin=board.GP11,pixel=4,num=7)
            )
        
        self.selects = (
            Select(self,pin=board.GP7,pixel=0,col=Col.RED),
            Select(self,pin=board.GP8,pixel=1,col=Col.GREEN),
            Select(self,pin=board.GP9,pixel=2,col=Col.BLUE),
            Select(self,pin=board.GP10,pixel=3,col=Col.YELLOW)
                   )
        
        self.sounds = (
            Keyboard(self,Col.RED,0),
            Rhythm(self,Col.GREEN,1),
            Rhythm(self,Col.BLUE,2),
            Rhythm(self,Col.YELLOW,3)
            )
        print("MidiBox 4.0 starting")
        print("Memory free:",gc.mem_free())
        self.note_volume = 120
        self.midi = adafruit_midi.MIDI(midi_out=usb_midi.ports[1], out_channel=0)
        self.buttons = self.notes + self.selects
        self.pixels = neopixel.NeoPixel(board.GP0,len(self.buttons),auto_write=False)
        self.pixels.brightness = 0.5
        self.settings_active=False
        self.settings_active = False
        self.select_voice(self.sounds[0].col)
        self.select_pixel = self.selects[0].pixel
        self.pixels.show()
        self.reset_time = False
        self.time = time.monotonic()
        self.euclid_played = False
        self.no_of_notes_pressed = 0
        self.no_of_selects_pressed = 0
        
    def update(self):
        self.time = time.monotonic()
        self.euclid_played = False
        
        for button in self.buttons:
            button.update()
        
        for sound in self.sounds:
            sound.update()
        
        self.reset_time = False
        self.pixels.show()
        
box = MidiBox()

while True:
    box.update()
