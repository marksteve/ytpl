(function($, undefined) {

  window.YTPL = {models: {}, collections: {}, views: {}};

  _(YTPL.models).extend({
    Video: Backbone.Model.extend({
    }),
    Listener: Backbone.Model.extend({
      initialize: function() {
        if (this.get('username')) {
          this.set('photo', 'http://graph.facebook.com/' + this.get('username') + '/picture');
        } else {
          this.set('photo', '/static/anon.jpg');
        }
      }
    })
  });

  _(YTPL.collections).extend({
    Results: Backbone.Collection.extend({
      model: YTPL.models.Video
    }),
    Playlist: Backbone.Collection.extend({
      model: YTPL.models.Video,
      url: function() {
        return '/pl/' + this.plName;
      },
      comparator: function(model) {
        return model.get('pos');
      },
      parse: function(response) {
        return response.videos;
      }
    }),
    Listeners: Backbone.Collection.extend({
      model: YTPL.models.Listener
    })
  });

  YTPL.views.Result = Backbone.View.extend({
    tagName: 'li',
    className: 'cf',
    events: {
      'click': 'addToPL'
    },
    template:
      '<img src="<%- thumbnail.url %>">' +
      '<h3 class="title"><%- title %></h3>' +
      '<span class="author"><%- author %></span>',
    render: function() {
      this.$el.html(_.template(this.template, this.model.toJSON()));
      return this;
    },
    addToPL: function(e) {
      // Wait for this since we need to assign an id to the element attribute as it renders
      // and the id is given after the post request succeeds
      YTPL.playlist.create(this.model.toJSON(), {wait: true});
      YTPL.results.reset([]);
    }
  });

  YTPL.views.Search = Backbone.View.extend({
    el: '#search',
    events: {
      'keyup input': 'checkKey'
    },
    initialize: function() {
      this.collection.on('reset', this.showResults, this);
    },
    checkKey: function(e) {
      if (e.keyCode == 13) {
        this.search();
      } else {
        var q = this.$('input').val();
        clearTimeout(self.keyTimeout);
        if (q) {
          self.keyTimeout = setTimeout(_.bind(this.search, this), 1000);
        } else {
          this.collection.reset([]);
        }
      }
    },
    search: function(e) {
      var q = this.$('input').val();
      var ytSearchURL = 'https://gdata.youtube.com/feeds/api/videos?orderby=relevance&max-results=10&v=2&alt=json';
      if (q) {
        YTPL.promise = $.ajax({
          url: ytSearchURL,
          data: {
            q: q
          },
          dataType: 'json'
        });
        YTPL.promise.done(_.bind(function(response) {
          var results = _(response.feed.entry).map(function(e) {
            var thumbnail = _(e.media$group.media$thumbnail).find(function(t) {
              return t.yt$name == 'hqdefault';
            });
            return {
              vid: e.media$group.yt$videoid.$t,
              author: e.author[0].name.$t,
              title: e.title.$t,
              thumbnail: thumbnail
            };
          });
          this.collection.reset(results);
        }, this));
      }
    },
    showResults: function(collection) {
      var $results = this.$('#results').empty();
      if (this.$('input').val() && collection.length > 0) {
        collection.each(function(model) {
          var view = new YTPL.views.Result({
            model: model
          });
          $results.append(view.render().el);
        }, this);
        $results.show();
      } else {
        this.$('input', this.$el).val('');
        $results.hide();
      }
    }
  });

  YTPL.views.Video = Backbone.View.extend({
    tagName: 'li',
    className: 'cf',
    events: {
      'click .title': 'play',
      'click img': 'play',
      'click .delete': 'delete'
    },
    template:
      '<img src="<%- thumbnail.url %>">' +
      '<a href="#" class="delete">&times;</a>' +
      '<h3 class="title"><%- title %></h3>' +
      '<span class="author"><%- author %></span>',
    render: function() {
      if (this.model.id) {
        this.$el.attr('id', this.model.id);
      }
      this.$el.html(_.template(this.template, this.model.toJSON()));
      if (!YTPL.canEdit) {
        // Remove delete button for non editors
        this.$('.delete').remove();
      }
      if (YTPL.player && YTPL.player.playing.id == this.model.id) {
        this.$el.addClass('playing');
      }
      return this;
    },
    play: function() {
      YTPL.player.playing = this.model;
      YTPL.player.play();
    },
    'delete': function(e, x, y, z) {
      e.preventDefault();
      this.model.destroy({
        success: _.bind(function(model, response) {
          this.remove();
          // Update positions
          _(response.videos).each(function(video) {
            YTPL.playlist.get(video.id).set('pos', video.pos);
          });
        }, this)
      });
    }
  });

  YTPL.views.Playlist = Backbone.View.extend({
    el: '#playlist',
    events: {
      'sortupdate': 'sort',
      'click .share': 'share'
    },
    initialize: function() {
      this.collection.on('add', this.addVideo, this);
      this.collection.on('reset', this.addVideos, this);
    },
    addVideos: function(collection) {
      var $ul = this.$('ul');
      if (this.collection.length > 0) {
        $ul.empty();
      }
      collection.each(this.addVideo, this);
      if (YTPL.canEdit) {
        $ul.sortable().disableSelection();
      }
    },
    addVideo: function(model, indexOrCollection) {
      var $ul = this.$('ul');
      // `add` passes the index while `create` passes the collection
      if (!_(indexOrCollection).isNumber()) {
        $ul.sortable().disableSelection();
      }
      if (this.collection.length == 1) {
        $ul.empty();
      }
      model.view = new YTPL.views.Video({
        model: model
      });
      $ul.append(model.view.render().el);
    },
    sort: function(e, ui) {
      var $video = ui.item;
      var id = $video.attr('id');
      var pos = _(this.$('ul').sortable('toArray')).indexOf(id);
      var video = this.collection.get(id);
      video.save({id: id, pos: pos}, {
        success: _.bind(function(model, response) {
          // Update positions
          _(response.videos).each(function(video) {
            YTPL.playlist.get(video.id).set('pos', video.pos);
          });
        }, this)
      });
    },
    share: function(e) {
      e.preventDefault();
      var $button = $(e.target);
      var promise = $.ajax({url: '/share/' + this.collection.plName});
      $button.html('Sharing&hellip;').prop('disabled', true);
      promise.done(function() {
        $button.html('Shared!');
      });
      promise.fail(function(){
        $button.html('Share failed!');
      });
      promise.always(function() {
        setTimeout(function() {
          $button.html('Share').prop('disabled', false);
        }, 3000);
      });
    }
  });

  YTPL.views.Player = Backbone.View.extend({
    playing: null,
    el: '#player',
    initialize: function() {
      this.collection.on('add', this.playFirstAdd, this);
    },
    setIframe: function() {
      this.ytPlayer = new YT.Player('player', {
        height: '270',
        width: '480',
        events: {
          'onReady': _.bind(this.ready, this),
          'onStateChange': _.bind(this.stateChange, this)
        }
      });
    },
    ready: function(e) {
      // Auto play first video
      this.playing = this.collection.at(0);
      this.play();
    },
    play: function() {
      if (this.playing) {
        this.ytPlayer.loadVideoById(this.playing.get('vid'));
        this.ytPlayer.playVideo();
        this.playing.view.$el.addClass('playing').siblings().removeClass('playing');
      }
    },
    playFirstAdd: function() {
      if (this.collection.length == 1) {
        this.play();
      }
    },
    stateChange: function(e) {
      // Next video
      if (e.data == YT.PlayerState.ENDED) {
        this.playing = this.collection.at(parseInt(this.playing.get('pos'), 10) + 1);
        if (!this.playing) {
          this.playing = this.collection.at(0);
        }
        this.play();
      }
    }
  });

  YTPL.views.Playlists = Backbone.View.extend({
    el: '#playlists',
    events: {
      'change select': 'switchPlaylist'
    },
    switchPlaylist: function(e) {
      var plName = this.$(e.target).val();
      if (plName.length > 0) {
        location.href = '/' + plName;
      }
    }
  });

  YTPL.views.Listener = Backbone.View.extend({
    tagName: 'li',
    template:
      '<img src="<%- photo %>"> <%- name %>',
    render: function() {
      this.$el.html(_.template(this.template, this.model.toJSON()));
      return this;
    }
  });

  YTPL.views.Listeners = Backbone.View.extend({
    el: '#listeners',
    initialize: function() {
      this.collection.on('add', this.addListener, this);
      this.collection.on('reset', this.addListeners, this);
      this.collection.on('remove', this.removeListener, this);
    },
    addListener: function(model) {
      var $ul = this.$('ul');
      model.view = new YTPL.views.Listener({
        model: model
      });
      $ul.append(model.view.render().el);
    },
    addListeners: function(collection) {
      collection.each(this.addListener, this);
    },
    removeListener: function(model) {
      model.view.remove();
    }
  });

  YTPL.results = new YTPL.collections.Results();
  YTPL.playlist = new YTPL.collections.Playlist();
  YTPL.listeners = new YTPL.collections.Listeners();

  YTPL.Router = Backbone.Router.extend({
    routes: {
      ':plName': 'default'
    },
    'default': function(plName) {
      new YTPL.views.Playlists();

      YTPL.results.plName = plName;
      YTPL.playlist.plName = plName;

      new YTPL.views.Search({collection: YTPL.results});
      new YTPL.views.Playlist({collection: YTPL.playlist});
      new YTPL.views.Listeners({collection: YTPL.listeners});

      YTPL.playlist.fetch({success: function() {
        YTPL.player = new YTPL.views.Player({collection: YTPL.playlist});
        YTPL.player.setIframe();

        YTPL.wsRetries = 0;

        YTPL.wsConnect = function() {
          if (YTPL.olInterval) {
            clearInterval(YTPL.olInterval);
          }

          YTPL.ws = new WebSocket(YTPL.wsURL);

          YTPL.ws.onopen = function() {
            console.log('Connected.');

            YTPL.ws.send(plName);
            YTPL.olInterval = setInterval(function() {
              YTPL.ws.send('ol');
            }, 3000);
          };

          var split, type, data;
          YTPL.ws.onmessage = function(e) {
            split = e.data.indexOf(':');
            action = e.data.substr(0, split);
            data = JSON.parse(e.data.substr(split + 1));
            switch (action) {
              case 'pl_reset':
                YTPL.playlist.reset(data.videos);
                break;
              case 'pl_add':
                YTPL.playlist.add(data.video);
                break;
              case 'pl_listeners':
                YTPL.listeners.reset(data);
                break;
              case 'pl_listen':
                YTPL.listeners.add(data);
                break;
              case 'pl_leave':
                YTPL.listeners.remove(data.id);
                break;
            }
          };

          YTPL.ws.onclose = function() {
            console.log('Reconnecting...');
            YTPL.wsRetries++;
            setTimeout(YTPL.wsConnect, Math.pow(2, YTPL.wsRetries) * 1000);
          };
        };

        YTPL.wsConnect();
      }});

      // Handle expired sessions
      $(document).ajaxError(function(e, xhr) {
        if (xhr.status == 401) {
          location.href = '/fbsignin?pl_name=' + plName;
        }
      });
    }
  });

})(jQuery);

function onYouTubePlayerAPIReady() {
  YTPL.router = new YTPL.Router();
  Backbone.history.start({pushState: true});
}